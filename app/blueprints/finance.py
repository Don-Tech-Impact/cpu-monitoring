"""
Finance blueprint
All routes require a valid JWT.  org_id is extracted from the token.

Routes:
  GET    /api/finance/transactions          — list (filters: type, from, to)
  POST   /api/finance/transactions          — record + update account balance
  GET    /api/finance/transactions/export/csv  (must be before /<id>)
  GET    /api/finance/transactions/<id>     — single transaction
  PUT    /api/finance/transactions/<id>     — update + adjust balance
  DELETE /api/finance/transactions/<id>     — delete + reverse balance

  GET    /api/finance/accounts              — list accounts
  POST   /api/finance/accounts              — create account
  GET    /api/finance/categories            — list finance categories
  POST   /api/finance/categories            — create finance category

  GET    /api/finance/summary               — current-month totals
  GET    /api/finance/cashflow              — last 6 months monthly totals
  GET    /api/finance/export/csv            — CSV of transactions
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app import database_connection

finance_bp = Blueprint("finance", __name__)


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------

def _row(row: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, (date, datetime))
            else (float(v) if isinstance(v, Decimal) else v))
        for k, v in row.items()
    }


# ===========================================================================
# TRANSACTIONS
# ===========================================================================

# ---------------------------------------------------------------------------
# GET /api/finance/transactions
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions", methods=["GET"])
@jwt_required()
def list_transactions():
    claims = get_jwt()
    org_id = claims.get("org_id")

    type_filter = request.args.get("type")
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT t.*, a.name AS account_name, fc.name AS category_name,
                   u.name AS recorded_by_name
            FROM transactions t
            LEFT JOIN accounts a ON a.id = t.account_id
            LEFT JOIN finance_categories fc ON fc.id = t.category_id
            LEFT JOIN users u ON u.id = t.recorded_by
            WHERE t.org_id = %s
        """
        params = [org_id]

        if type_filter:
            query += " AND t.type = %s"
            params.append(type_filter)
        if from_date:
            query += " AND t.transaction_date >= %s"
            params.append(from_date)
        if to_date:
            query += " AND t.transaction_date <= %s"
            params.append(to_date)

        query += " ORDER BY t.transaction_date DESC, t.created_at DESC"
        cursor.execute(query, params)
        transactions = [_row(r) for r in cursor.fetchall()]
        return jsonify({"transactions": transactions, "count": len(transactions)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/finance/transactions
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions", methods=["POST"])
@jwt_required()
def create_transaction():
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = identity["user_id"]

    data = request.get_json(silent=True) or {}

    required = ["account_id", "type", "amount", "transaction_date"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    if data["type"] not in ("income", "expense", "transfer"):
        return jsonify({"error": "type must be income, expense, or transfer"}), 400

    try:
        amount = Decimal(str(data["amount"]))
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        return jsonify({"error": "amount must be a positive number"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Verify account belongs to org
        cursor.execute(
            "SELECT id, balance FROM accounts WHERE id = %s AND org_id = %s",
            (data["account_id"], org_id),
        )
        account = cursor.fetchone()
        if not account:
            return jsonify({"error": "Account not found"}), 404

        # Insert transaction
        cursor.execute(
            """INSERT INTO transactions
               (org_id, account_id, category_id, type, amount, description,
                reference, transaction_date, recorded_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                org_id,
                data["account_id"],
                data.get("category_id"),
                data["type"],
                float(amount),
                data.get("description"),
                data.get("reference"),
                data["transaction_date"],
                user_id,
            ),
        )
        txn_id = cursor.lastrowid

        # Update account balance
        if data["type"] == "income":
            cursor.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (float(amount), data["account_id"]),
            )
        elif data["type"] == "expense":
            cursor.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (float(amount), data["account_id"]),
            )
        # transfer: balance adjustment handled externally (two separate transactions)

        conn.commit()
        return jsonify({"message": "Transaction recorded", "transaction_id": txn_id}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/finance/transactions/export/csv  (before /<id> to avoid conflict)
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions/export/csv", methods=["GET"])
@jwt_required()
def export_transactions_csv_sub():
    """Alias so both /export/csv paths work."""
    return _export_transactions_csv()


# ---------------------------------------------------------------------------
# GET /api/finance/transactions/<id>
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions/<int:txn_id>", methods=["GET"])
@jwt_required()
def get_transaction(txn_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT t.*, a.name AS account_name, fc.name AS category_name,
                      u.name AS recorded_by_name
               FROM transactions t
               LEFT JOIN accounts a ON a.id = t.account_id
               LEFT JOIN finance_categories fc ON fc.id = t.category_id
               LEFT JOIN users u ON u.id = t.recorded_by
               WHERE t.id = %s AND t.org_id = %s""",
            (txn_id, org_id),
        )
        txn = cursor.fetchone()
        if not txn:
            return jsonify({"error": "Transaction not found"}), 404

        return jsonify({"transaction": _row(txn)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /api/finance/transactions/<id>
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions/<int:txn_id>", methods=["PUT"])
@jwt_required()
def update_transaction(txn_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "No data provided"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Fetch existing
        cursor.execute(
            "SELECT * FROM transactions WHERE id = %s AND org_id = %s",
            (txn_id, org_id),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Transaction not found"}), 404

        old_amount = Decimal(str(existing["amount"]))
        old_type = existing["type"]
        old_account_id = existing["account_id"]

        # Determine new values
        new_amount = Decimal(str(data.get("amount", old_amount)))
        new_type = data.get("type", old_type)
        new_account_id = data.get("account_id", old_account_id)

        # Reverse old balance effect
        if old_type == "income":
            cursor.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (float(old_amount), old_account_id),
            )
        elif old_type == "expense":
            cursor.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (float(old_amount), old_account_id),
            )

        # Apply new balance effect
        if new_type == "income":
            cursor.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (float(new_amount), new_account_id),
            )
        elif new_type == "expense":
            cursor.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (float(new_amount), new_account_id),
            )

        # Update transaction record
        allowed = ["account_id", "category_id", "type", "amount",
                   "description", "reference", "transaction_date"]
        updates = {k: v for k, v in data.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [txn_id, org_id]
            cursor.execute(
                f"UPDATE transactions SET {set_clause} WHERE id = %s AND org_id = %s",
                values,
            )

        conn.commit()
        return jsonify({"message": "Transaction updated"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# DELETE /api/finance/transactions/<id>
# ---------------------------------------------------------------------------
@finance_bp.route("/api/finance/transactions/<int:txn_id>", methods=["DELETE"])
@jwt_required()
def delete_transaction(txn_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM transactions WHERE id = %s AND org_id = %s",
            (txn_id, org_id),
        )
        txn = cursor.fetchone()
        if not txn:
            return jsonify({"error": "Transaction not found"}), 404

        amount = Decimal(str(txn["amount"]))

        # Reverse balance
        if txn["type"] == "income":
            cursor.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s",
                (float(amount), txn["account_id"]),
            )
        elif txn["type"] == "expense":
            cursor.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s",
                (float(amount), txn["account_id"]),
            )

        cursor.execute(
            "DELETE FROM transactions WHERE id = %s AND org_id = %s",
            (txn_id, org_id),
        )
        conn.commit()
        return jsonify({"message": "Transaction deleted and balance reversed"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ===========================================================================
# ACCOUNTS
# ===========================================================================

@finance_bp.route("/api/finance/accounts", methods=["GET"])
@jwt_required()
def list_accounts():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM accounts WHERE org_id = %s ORDER BY name",
            (org_id,),
        )
        accounts = [_row(r) for r in cursor.fetchall()]
        return jsonify({"accounts": accounts}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@finance_bp.route("/api/finance/accounts", methods=["POST"])
@jwt_required()
def create_account():
    claims = get_jwt()
    org_id = claims.get("org_id")

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Account name is required"}), 400

    acc_type = data.get("type", "cash")
    if acc_type not in ("cash", "bank", "mobile_money", "other"):
        return jsonify({"error": "type must be cash, bank, mobile_money, or other"}), 400

    balance = data.get("balance", 0)

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO accounts (org_id, name, type, balance) VALUES (%s,%s,%s,%s)",
            (org_id, name, acc_type, balance),
        )
        acc_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "message": "Account created",
            "account": {"id": acc_id, "org_id": org_id, "name": name,
                        "type": acc_type, "balance": balance},
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ===========================================================================
# FINANCE CATEGORIES
# ===========================================================================

@finance_bp.route("/api/finance/categories", methods=["GET"])
@jwt_required()
def list_finance_categories():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM finance_categories WHERE org_id = %s ORDER BY type, name",
            (org_id,),
        )
        categories = cursor.fetchall()
        return jsonify({"categories": categories}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@finance_bp.route("/api/finance/categories", methods=["POST"])
@jwt_required()
def create_finance_category():
    claims = get_jwt()
    org_id = claims.get("org_id")

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    cat_type = data.get("type")

    if not name:
        return jsonify({"error": "Category name is required"}), 400
    if cat_type not in ("income", "expense"):
        return jsonify({"error": "type must be income or expense"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO finance_categories (org_id, name, type) VALUES (%s,%s,%s)",
            (org_id, name, cat_type),
        )
        cat_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "message": "Category created",
            "category": {"id": cat_id, "org_id": org_id, "name": name, "type": cat_type},
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ===========================================================================
# SUMMARY & CASHFLOW
# ===========================================================================

@finance_bp.route("/api/finance/summary", methods=["GET"])
@jwt_required()
def finance_summary():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS total_income,
                 COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS total_expense
               FROM transactions
               WHERE org_id = %s
                 AND YEAR(transaction_date)  = YEAR(CURDATE())
                 AND MONTH(transaction_date) = MONTH(CURDATE())""",
            (org_id,),
        )
        row = cursor.fetchone()
        total_income = float(row["total_income"])
        total_expense = float(row["total_expense"])

        now = datetime.utcnow()
        return jsonify({
            "total_income": total_income,
            "total_expense": total_expense,
            "net": round(total_income - total_expense, 2),
            "period": f"{now.year}-{now.month:02d}",
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@finance_bp.route("/api/finance/cashflow", methods=["GET"])
@jwt_required()
def finance_cashflow():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT
                 DATE_FORMAT(transaction_date, '%%Y-%%m') AS month,
                 COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS income,
                 COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS expense
               FROM transactions
               WHERE org_id = %s
                 AND transaction_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
               GROUP BY DATE_FORMAT(transaction_date, '%%Y-%%m')
               ORDER BY month ASC""",
            (org_id,),
        )
        rows = cursor.fetchall()
        cashflow = [
            {
                "month": r["month"],
                "income": float(r["income"]),
                "expense": float(r["expense"]),
                "net": round(float(r["income"]) - float(r["expense"]), 2),
            }
            for r in rows
        ]
        return jsonify({"cashflow": cashflow}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ===========================================================================
# CSV EXPORT
# ===========================================================================

def _export_transactions_csv():
    """Internal helper used by both export routes."""
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT t.id, t.transaction_date, t.type, t.amount,
                      a.name AS account, fc.name AS category,
                      t.description, t.reference,
                      u.name AS recorded_by, t.created_at
               FROM transactions t
               LEFT JOIN accounts a ON a.id = t.account_id
               LEFT JOIN finance_categories fc ON fc.id = t.category_id
               LEFT JOIN users u ON u.id = t.recorded_by
               WHERE t.org_id = %s
               ORDER BY t.transaction_date DESC""",
            (org_id,),
        )
        rows = cursor.fetchall()

        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    k: (v.isoformat() if isinstance(v, (date, datetime))
                        else (float(v) if isinstance(v, Decimal) else v))
                    for k, v in row.items()
                })
        else:
            output.write("No transactions found\n")

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=transactions.csv"},
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@finance_bp.route("/api/finance/export/csv", methods=["GET"])
@jwt_required()
def export_transactions_csv():
    return _export_transactions_csv()
