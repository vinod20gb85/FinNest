from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    session,
)
import os
from datetime import datetime
from urllib.parse import quote

import app
import subscription_app as subscription
from income_routes import income_bp
from dotenv import load_dotenv

load_dotenv()

server = Flask(__name__)
server.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
server.register_blueprint(income_bp)

HOST = "0.0.0.0"
PORT = 5000


# ============================================================
# Existing Finance App
# ============================================================

@server.route("/")
def index():
    return render_template("index.html")


@server.route("/api/summary")
def summary():
    income, expenses, balance = app.get_transaction_summary()

    return jsonify({
        "income": income,
        "expenses": expenses,
        "balance": balance
    })


@server.route("/api/report")
def monthly_report():
    month = request.args.get("month")

    if month:
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError:
            return jsonify({
                "error": "Invalid month. Please use YYYY-MM."
            }), 400

    report = app.get_monthly_report(month)

    return jsonify({"report": report})


@server.route("/api/yearly-report")
def yearly_report():
    year = request.args.get("year")

    if year:
        try:
            year_int = int(year)
            if year_int < 2000 or year_int > 2100:
                raise ValueError
        except ValueError:
            return jsonify({
                "error": "Invalid year. Please use YYYY."
            }), 400

    report = app.get_yearly_report(year)

    return jsonify({"report": report})


@server.route("/api/transactions")
def transactions():
    month = request.args.get("month")

    if month:
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError:
            return jsonify({
                "error": "Invalid month. Please use YYYY-MM."
            }), 400

    rows = app.get_recent_transactions(limit=20, month=month)

    transactions = []

    for (
        transaction_id,
        date,
        tx_type,
        amount,
        category,
        description
    ) in rows:
        transactions.append({
            "id": transaction_id,
            "date": date,
            "type": tx_type,
            "amount": amount,
            "category": category,
            "description": description or ""
        })

    return jsonify({"transactions": transactions})


@server.route(
    "/api/transaction/<int:transaction_id>",
    methods=["DELETE"]
)
def delete_transaction(transaction_id):
    try:
        app.delete_transaction(transaction_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route("/api/transaction", methods=["POST"])
def add_transaction():
    try:
        data = request.get_json(silent=True) or {}

        transaction_type = str(
            data.get("type", "")
        ).strip().lower()

        if transaction_type not in ("income", "expense"):
            return jsonify({
                "error": "Type must be income or expense."
            }), 400

        try:
            amount = float(data.get("amount", 0))
        except (ValueError, TypeError):
            amount = 0

        if amount <= 0:
            return jsonify({
                "error": "Amount must be greater than zero."
            }), 400

        category = str(
            data.get("category", "Other")
        ).strip() or "Other"

        category = app.normalize_category(category)

        description = str(
            data.get("description", "")
        ).strip()

        transaction_date = str(
            data.get("transaction_date", "")
        ).strip()

        if not transaction_date:
            return jsonify({
                "error": "Transaction date is required."
            }), 400

        try:
            datetime.strptime(transaction_date, "%Y-%m-%d")
        except ValueError:
            return jsonify({
                "error": "Invalid date. Use YYYY-MM-DD."
            }), 400

        transaction = {
            "type": transaction_type,
            "amount": amount,
            "currency": "INR",
            "category": category,
            "description": description,
            "transaction_date": transaction_date
        }

        app.add_transaction(transaction)

        return jsonify({
            "success": True,
            "transaction": transaction
        }), 201

    except Exception as error:
        return jsonify({"error": str(error)}), 500


# ============================================================
# Subscription Manager
#
# This keeps subscriptions in the separate subscriptions.db
# used by subscription_app.py.
# ============================================================

@server.route("/subscriptions")
def subscriptions_page():
    return render_template("subscriptions.html")


@server.route("/api/gmail/status")
def gmail_status():
    try:
        return jsonify(subscription.gmail_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _gmail_redirect_uri():
    configured = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return request.url_root.rstrip("/") + "/api/gmail/oauth2callback"


@server.route("/api/gmail/connect")
def gmail_connect():
    try:
        status = subscription.gmail_status()
        if not status.get("available"):
            return jsonify(status), 400

        redirect_uri = _gmail_redirect_uri()
        oauth = subscription.begin_gmail_oauth(redirect_uri)
        session["gmail_oauth_state"] = oauth["state"]
        session["gmail_oauth_code_verifier"] = oauth.get("code_verifier")
        session["gmail_oauth_redirect_uri"] = redirect_uri

        # Browser navigation takes the user directly to Google's sign-in/consent page.
        return redirect(oauth["authorization_url"])
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@server.route("/api/gmail/oauth2callback")
def gmail_oauth_callback():
    error = request.args.get("error")
    if error:
        return redirect("/subscriptions?gmail=error&message=" + quote(error))

    state = session.pop("gmail_oauth_state", None)
    code_verifier = session.pop("gmail_oauth_code_verifier", None)
    redirect_uri = session.pop("gmail_oauth_redirect_uri", None) or _gmail_redirect_uri()

    if not state:
        return redirect("/subscriptions?gmail=error&message=OAuth%20session%20expired")

    try:
        subscription.complete_gmail_oauth(
            request.url,
            state,
            redirect_uri,
            code_verifier,
        )
        return redirect("/subscriptions?gmail=connected")
    except Exception as e:
        return redirect("/subscriptions?gmail=error&message=" + quote(str(e)))


@server.route("/api/gmail/scan", methods=["POST"])
def gmail_scan():
    try:
        data = request.get_json(silent=True) or {}
        max_results = int(data.get("max_results", 50))
        newer_than = str(data.get("newer_than", "180d"))
        return jsonify({
            "candidates": subscription.scan_gmail_subscriptions(
                max_results=max_results, newer_than=newer_than
            )
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@server.route("/api/gmail/import", methods=["POST"])
def gmail_import():
    try:
        data = request.get_json(silent=True) or {}
        candidate = dict(data)
        for key in ("message_id", "thread_id", "email_subject", "email_from", "email_date", "confidence", "existing_match"):
            candidate.pop(key, None)

        existing = subscription.list_subscriptions(status="All", search=candidate.get("name", ""))
        if any(x["name"].strip().lower() == str(candidate.get("name", "")).strip().lower() for x in existing):
            return jsonify({"error": "A subscription with this name already exists."}), 409

        item = subscription.add_subscription(candidate)
        return jsonify({"subscription": item}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@server.route("/api/subscription-summary")
def subscription_summary():
    try:
        return jsonify(subscription.get_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# The subscription UI expects /api/summary.
# Because the finance app already owns /api/summary, the UI
# below has been adjusted to call /api/subscription-summary.
# All other subscription endpoints remain under /api/subscriptions.

@server.route("/api/categories")
def subscription_categories():
    try:
        return jsonify({
            "categories": subscription.get_category_summary()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route("/api/upcoming")
def subscription_upcoming():
    try:
        days = request.args.get("days", "30")
        return jsonify({
            "upcoming": subscription.get_upcoming(days)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@server.route("/api/subscriptions", methods=["GET"])
def list_subscriptions():
    try:
        status = request.args.get("status", "All")
        search = request.args.get("search", "")

        return jsonify({
            "subscriptions": subscription.list_subscriptions(
                status=status,
                search=search
            )
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route("/api/subscriptions", methods=["POST"])
def create_subscription():
    try:
        data = request.get_json(silent=True) or {}
        item = subscription.add_subscription(data)
        return jsonify({"subscription": item}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@server.route("/api/subscriptions/<int:subscription_id>")
def get_subscription(subscription_id):
    try:
        item = subscription.get_subscription(subscription_id)

        if not item:
            return jsonify({
                "error": "Subscription not found."
            }), 404

        return jsonify({"subscription": item})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(
    "/api/subscriptions/<int:subscription_id>",
    methods=["PUT"]
)
def edit_subscription(subscription_id):
    try:
        data = request.get_json(silent=True) or {}

        item = subscription.update_subscription(
            subscription_id,
            data
        )

        return jsonify({"subscription": item})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(
    "/api/subscriptions/<int:subscription_id>",
    methods=["DELETE"]
)
def remove_subscription(subscription_id):
    try:
        subscription.delete_subscription(subscription_id)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(
    "/api/subscriptions/<int:subscription_id>/status",
    methods=["POST"]
)
def change_subscription_status(subscription_id):
    try:
        data = request.get_json(silent=True) or {}

        item = subscription.set_status(
            subscription_id,
            data.get("status")
        )

        return jsonify({"subscription": item})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(
    "/api/subscriptions/<int:subscription_id>/payments",
    methods=["GET"]
)
def subscription_payments(subscription_id):
    try:
        return jsonify({
            "payments": subscription.get_payment_history(
                subscription_id
            )
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route(
    "/api/subscriptions/<int:subscription_id>/payments",
    methods=["POST"]
)
def add_subscription_payment(subscription_id):
    try:
        data = request.get_json(silent=True) or {}

        subscription.record_payment(
            subscription_id,
            data.get("payment_date"),
            data.get("amount"),
            data.get("notes", "")
        )

        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# Startup
# ============================================================

# Subscription UI is kept separately in templates/subscriptions.html.

if __name__ == "__main__":
    app.init_db()
    subscription.init_db()

    server.run(
        host=HOST,
        port=PORT,
        debug=False
    )
