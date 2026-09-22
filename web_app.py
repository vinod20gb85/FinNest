from flask import (
    Flask,
    jsonify,
    render_template,
    request
)
from datetime import datetime

import app


server = Flask(__name__)

HOST = "0.0.0.0"
PORT = 5000


# -----------------------------
# Dashboard
# -----------------------------

@server.route("/")
def index():
    return render_template("index.html")


# -----------------------------
# Summary
# -----------------------------

@server.route("/api/summary")
def summary():

    income, expenses, balance = (
        app.get_transaction_summary()
    )

    return jsonify({
        "income": income,
        "expenses": expenses,
        "balance": balance
    })


# -----------------------------
# Monthly Report
# -----------------------------

@server.route("/api/report")
def monthly_report():

    month = request.args.get("month")

    if month:
        try:
            datetime.strptime(
                month,
                "%Y-%m"
            )
        except ValueError:
            return jsonify({
                "error":
                    "Invalid month. Please use YYYY-MM."
            }), 400

    report = app.get_monthly_report(
        month
    )

    return jsonify({
        "report": report
    })


# -----------------------------
# Yearly Report
# -----------------------------

@server.route("/api/yearly-report")
def yearly_report():

    year = request.args.get("year")

    if year:

        try:
            year_int = int(year)

            if (
                year_int < 2000
                or year_int > 2100
            ):
                raise ValueError

        except ValueError:

            return jsonify({
                "error":
                    "Invalid year. Please use YYYY."
            }), 400

    report = app.get_yearly_report(
        year
    )

    return jsonify({
        "report": report
    })


# -----------------------------
# Transactions
# -----------------------------

@server.route("/api/transactions")
def transactions():

    month = request.args.get("month")

    if month:

        try:
            datetime.strptime(
                month,
                "%Y-%m"
            )

        except ValueError:

            return jsonify({
                "error":
                    "Invalid month. Please use YYYY-MM."
            }), 400

    rows = app.get_recent_transactions(
        limit=20,
        month=month
    )

    transactions = []

    for (
		id,
        date,
        tx_type,
        amount,
        category,
        description
    ) in rows:

        transactions.append({
			"id": id,
            "date": date,
            "type": tx_type,
            "amount": amount,
            "category": category,
            "description": description or ""
        })

    return jsonify({
        "transactions": transactions
    })

# -----------------------------
# Delete Transaction
# -----------------------------
@server.route("/api/transaction/<int:transaction_id>", methods=["DELETE"])
def delete_transaction(transaction_id):
    try:
        app.delete_transaction(transaction_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
# -----------------------------
# Add Transaction
# -----------------------------

@server.route(
    "/api/transaction",
    methods=["POST"]
)
def add_transaction():

    try:

        data = request.get_json(
            silent=True
        ) or {}

        # -------------------------
        # Type
        # -------------------------

        transaction_type = str(
            data.get("type", "")
        ).strip().lower()

        if transaction_type not in (
            "income",
            "expense"
        ):

            return jsonify({
                "error":
                    "Type must be income or expense."
            }), 400

        # -------------------------
        # Amount
        # -------------------------

        try:
            amount = float(
                data.get("amount", 0)
            )
        except (ValueError, TypeError):
            amount = 0

        if amount <= 0:

            return jsonify({
                "error":
                    "Amount must be greater than zero."
            }), 400

        # -------------------------
        # Category
        # -------------------------

        category = str(
            data.get(
                "category",
                "Other"
            )
        ).strip()

        if not category:
            category = "Other"

        category = app.normalize_category(
            category
        )

        # -------------------------
        # Description
        # -------------------------

        description = str(
            data.get(
                "description",
                ""
            )
        ).strip()

        # -------------------------
        # Date
        # -------------------------

        transaction_date = str(
            data.get(
                "transaction_date",
                ""
            )
        ).strip()

        if not transaction_date:

            return jsonify({
                "error":
                    "Transaction date is required."
            }), 400

        try:

            datetime.strptime(
                transaction_date,
                "%Y-%m-%d"
            )

        except ValueError:

            return jsonify({
                "error":
                    "Invalid date. Use YYYY-MM-DD."
            }), 400

        # -------------------------
        # Save
        # -------------------------

        transaction = {
            "type": transaction_type,
            "amount": amount,
            "currency": "INR",
            "category": category,
            "description": description,
            "transaction_date":
                transaction_date
        }

        app.add_transaction(
            transaction
        )

        return jsonify({
            "success": True,
            "transaction": transaction
        }), 201

    except Exception as error:

        return jsonify({
            "error": str(error)
        }), 500


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":

    app.init_db()

    server.run(
        host=HOST,
        port=PORT,
        debug=False
    )
