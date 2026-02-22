"""
Dashboard blueprint

Routes:
  GET /api/dashboard  — aggregated summary (JWT required)
  GET /health         — health check (no auth)
"""

from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt, jwt_required

from app import database_connection

dashboard_bp = Blueprint("dashboard", __name__)


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _row(row: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, (date, datetime))
            else (float(v) if isinstance(v, Decimal) else v))
        for k, v in row.items()
    }


# ---------------------------------------------------------------------------
# GET /api/dashboard
# ---------------------------------------------------------------------------
@dashboard_bp.route("/api/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # ---- Asset summary ------------------------------------------------
        cursor.execute(
            """SELECT
                 COUNT(*) AS total,
                 COALESCE(SUM(CASE WHEN status='active'      THEN 1 ELSE 0 END), 0) AS active,
                 COALESCE(SUM(CASE WHEN status='maintenance' THEN 1 ELSE 0 END), 0) AS maintenance,
                 COALESCE(SUM(CASE WHEN status='disposed'    THEN 1 ELSE 0 END), 0) AS disposed,
                 COALESCE(SUM(CASE WHEN status='lost'        THEN 1 ELSE 0 END), 0) AS lost,
                 COALESCE(SUM(current_value), 0) AS total_value
               FROM assets
               WHERE org_id = %s""",
            (org_id,),
        )
        asset_row = cursor.fetchone()
        asset_summary = {
            "total": int(asset_row["total"]),
            "active": int(asset_row["active"]),
            "maintenance": int(asset_row["maintenance"]),
            "disposed": int(asset_row["disposed"]),
            "lost": int(asset_row["lost"]),
            "total_value": float(asset_row["total_value"]),
        }

        # ---- Finance summary (current month) --------------------------------
        cursor.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS monthly_income,
                 COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS monthly_expense
               FROM transactions
               WHERE org_id = %s
                 AND YEAR(transaction_date)  = YEAR(CURDATE())
                 AND MONTH(transaction_date) = MONTH(CURDATE())""",
            (org_id,),
        )
        fin_row = cursor.fetchone()
        monthly_income = float(fin_row["monthly_income"])
        monthly_expense = float(fin_row["monthly_expense"])

        # ---- Account balances -----------------------------------------------
        cursor.execute(
            "SELECT id, name, type, balance FROM accounts WHERE org_id = %s ORDER BY name",
            (org_id,),
        )
        accounts = [_row(r) for r in cursor.fetchall()]

        finance_summary = {
            "monthly_income": monthly_income,
            "monthly_expense": monthly_expense,
            "net": round(monthly_income - monthly_expense, 2),
            "accounts": accounts,
        }

        # ---- Recent transactions (last 5) -----------------------------------
        cursor.execute(
            """SELECT t.id, t.transaction_date, t.type, t.amount,
                      t.description, a.name AS account_name,
                      fc.name AS category_name
               FROM transactions t
               LEFT JOIN accounts a ON a.id = t.account_id
               LEFT JOIN finance_categories fc ON fc.id = t.category_id
               WHERE t.org_id = %s
               ORDER BY t.transaction_date DESC, t.created_at DESC
               LIMIT 5""",
            (org_id,),
        )
        recent_transactions = [_row(r) for r in cursor.fetchall()]

        # ---- Recent assets (last 5 added) -----------------------------------
        cursor.execute(
            """SELECT a.id, a.asset_tag, a.name, a.status,
                      a.current_value, a.location, a.created_at,
                      c.name AS category_name
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.org_id = %s
               ORDER BY a.created_at DESC
               LIMIT 5""",
            (org_id,),
        )
        recent_assets = [_row(r) for r in cursor.fetchall()]

        return jsonify({
            "assets": asset_summary,
            "finance": finance_summary,
            "recent_transactions": recent_transactions,
            "recent_assets": recent_assets,
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /health  — no auth required
# ---------------------------------------------------------------------------
@dashboard_bp.route("/health", methods=["GET"])
def health():
    conn = database_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM organizations")
            org_count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return jsonify({
                "status": "healthy",
                "database": "connected",
                "organizations": org_count,
            }), 200
        except Exception as e:
            return jsonify({"status": "unhealthy", "error": str(e)}), 500
    return jsonify({"status": "unhealthy", "database": "unavailable"}), 500
