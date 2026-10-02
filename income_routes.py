from flask import Blueprint, jsonify, render_template, request
import income_app as income

income_bp = Blueprint("income", __name__)


@income_bp.route("/income")
def income_page():
    return render_template("income.html")


@income_bp.route("/api/dashboard")
def dashboard():
    try:
        return jsonify(income.dashboard())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/asset-summary")
def asset_summary():
    try:
        return jsonify({"summary": income.asset_summary()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/investments", methods=["GET"])
def list_investments():
    try:
        status = request.args.get("status", "All")
        asset_type = request.args.get("asset_type", "All")
        search = request.args.get("search", "")
        return jsonify({
            "investments": income.list_investments(status, asset_type, search)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/investments", methods=["POST"])
def create_investment():
    try:
        data = request.get_json(silent=True) or {}
        print("POST /api/investments DATA:", data, flush=True)
        result = income.add_investment(data)
        return jsonify({"investment": result}), 201
    except Exception as e:
        print("POST /api/investments ERROR:", repr(e), flush=True)
        return jsonify({"error": str(e)}), 400


@income_bp.route("/api/investments/<int:investment_id>", methods=["GET"])
def get_investment(investment_id):
    try:
        result = income.get_investment(investment_id)
        if not result:
            return jsonify({"error": "Investment not found."}), 404
        return jsonify({"investment": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/investments/<int:investment_id>", methods=["PUT"])
def update_investment(investment_id):
    try:
        data = request.get_json(silent=True) or {}
        return jsonify({
            "investment": income.update_investment(investment_id, data)
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/investments/<int:investment_id>/status", methods=["POST"])
def investment_status(investment_id):
    try:
        data = request.get_json(silent=True) or {}
        return jsonify({
            "investment": income.set_status(investment_id, data.get("status"))
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/investments/<int:investment_id>/income", methods=["POST"])
def record_investment_income(investment_id):
    try:
        data = request.get_json(silent=True) or {}
        return jsonify({
            "income": income.record_income(investment_id, data)
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/income", methods=["GET"])
def list_income():
    try:
        status = request.args.get("status", "All")
        investment_id = request.args.get("investment_id")
        if investment_id not in (None, ""):
            try:
                investment_id = int(investment_id)
            except ValueError:
                return jsonify({"error": "Invalid investment_id."}), 400
        else:
            investment_id = None
        return jsonify({
            "income": income.list_income(status, investment_id)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@income_bp.route("/api/upcoming-income", methods=["GET"])
def upcoming_income():
    try:
        days = request.args.get("days", "90")
        return jsonify({"upcoming": income.upcoming_income(days)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@income_bp.route("/api/maturities", methods=["GET"])
def maturities():
    try:
        days = request.args.get("days", "90")
        return jsonify({"maturities": income.maturities(days)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
