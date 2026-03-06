"""
Branches blueprint — multi-branch support (Hospital use case)
Routes (all prefixed with /api/v1 in app.py):
  GET    /branches                      — list branches for org
  POST   /branches                      — create branch (admin only)
  GET    /branches/<id>                 — single branch with counts
  PUT    /branches/<id>                 — update branch (admin only)
  DELETE /branches/<id>                 — soft-delete (admin only)
  GET    /branches/<id>/assets          — assets in branch
  GET    /branches/<id>/summary         — financial summary for branch
  POST   /assets/<asset_id>/transfer    — transfer asset between branches
"""

import json
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt

from app import database_connection, require_org

branches_bp = Blueprint("branches", __name__)


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------
def _row(row: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, (date, datetime))
            else (float(v) if isinstance(v, Decimal) else v))
        for k, v in row.items()
    }


def _require_admin(claims: dict):
    """Return error response tuple if user is not admin, else None."""
    if claims.get("role") not in ("admin",) and not claims.get("is_superadmin"):
        return jsonify({"success": False, "error": "Admin access required"}), 403
    return None


def _require_admin_or_manager(claims: dict):
    if claims.get("role") not in ("admin", "manager") and not claims.get("is_superadmin"):
        return jsonify({"success": False, "error": "Manager or admin access required"}), 403
    return None


# ---------------------------------------------------------------------------
# GET /branches
# ---------------------------------------------------------------------------
@branches_bp.route("/branches", methods=["GET"])
@require_org
def list_branches():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        user_role = claims.get("role")
        user_branch_id = claims.get("branch_id")
        
        query = """SELECT b.*,
                      COUNT(DISTINCT a.id) AS asset_count,
                      COUNT(DISTINCT t.id) AS transaction_count
               FROM branches b
               LEFT JOIN assets a ON a.branch_id = b.id AND a.status != 'disposed'
               LEFT JOIN transactions t ON t.branch_id = b.id
               WHERE b.org_id = %s"""
        params = [org_id]
        
        # Branch scoping: if manager with branch_id, only show that branch
        if user_role == "manager" and user_branch_id:
            query += " AND b.id = %s"
            params.append(user_branch_id)
        
        query += " GROUP BY b.id ORDER BY b.name"
        
        cursor.execute(query, params)
        branches = [_row(r) for r in cursor.fetchall()]
        return jsonify({"success": True, "branches": branches, "count": len(branches)}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /branches
# ---------------------------------------------------------------------------
@branches_bp.route("/branches", methods=["POST"])
@require_org
def create_branch():
    claims = get_jwt()
    org_id = claims.get("org_id")

    err = _require_admin(claims)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "Branch name is required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Check name uniqueness within org
        cursor.execute(
            "SELECT id FROM branches WHERE org_id = %s AND name = %s",
            (org_id, name),
        )
        if cursor.fetchone():
            return jsonify({"success": False, "error": "Branch name already exists"}), 409

        cursor.execute(
            """INSERT INTO branches (org_id, name, code, address, phone)
               VALUES (%s, %s, %s, %s, %s)""",
            (org_id, name, data.get("code"), data.get("address"), data.get("phone")),
        )
        branch_id = cursor.lastrowid
        conn.commit()

        cursor.execute("SELECT * FROM branches WHERE id = %s", (branch_id,))
        branch = _row(cursor.fetchone())
        return jsonify({"success": True, "message": "Branch created", "branch": branch}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /branches/<id>
# ---------------------------------------------------------------------------
@branches_bp.route("/branches/<int:branch_id>", methods=["GET"])
@require_org
def get_branch(branch_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT b.*,
                      COUNT(DISTINCT a.id) AS asset_count,
                      COUNT(DISTINCT t.id) AS transaction_count,
                      COALESCE(SUM(CASE WHEN t.type='income' THEN t.amount ELSE 0 END), 0) AS total_income,
                      COALESCE(SUM(CASE WHEN t.type='expense' THEN t.amount ELSE 0 END), 0) AS total_expense
               FROM branches b
               LEFT JOIN assets a ON a.branch_id = b.id AND a.status != 'disposed'
               LEFT JOIN transactions t ON t.branch_id = b.id
               WHERE b.id = %s AND b.org_id = %s
               GROUP BY b.id""",
            (branch_id, org_id),
        )
        branch = cursor.fetchone()
        if not branch:
            return jsonify({"success": False, "error": "Branch not found"}), 404

        return jsonify({"success": True, "branch": _row(branch)}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /branches/<id>
# ---------------------------------------------------------------------------
@branches_bp.route("/branches/<int:branch_id>", methods=["PUT"])
@require_org
def update_branch(branch_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    err = _require_admin(claims)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM branches WHERE id = %s AND org_id = %s",
            (branch_id, org_id),
        )
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Branch not found"}), 404

        allowed = ["name", "code", "address", "phone", "is_active"]
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return jsonify({"success": False, "error": "No valid fields to update"}), 400

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [branch_id, org_id]
        cursor.execute(
            f"UPDATE branches SET {set_clause} WHERE id = %s AND org_id = %s",
            values,
        )
        conn.commit()

        cursor.execute("SELECT * FROM branches WHERE id = %s", (branch_id,))
        branch = _row(cursor.fetchone())
        return jsonify({"success": True, "message": "Branch updated", "branch": branch}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# DELETE /branches/<id>  — soft delete
# ---------------------------------------------------------------------------
@branches_bp.route("/branches/<int:branch_id>", methods=["DELETE"])
@require_org
def delete_branch(branch_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    err = _require_admin(claims)
    if err:
        return err

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id FROM branches WHERE id = %s AND org_id = %s",
            (branch_id, org_id),
        )
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Branch not found"}), 404

        cursor.execute(
            "UPDATE branches SET is_active = FALSE WHERE id = %s AND org_id = %s",
            (branch_id, org_id),
        )
        conn.commit()
        return jsonify({"success": True, "message": "Branch deactivated"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /branches/<id>/assets
# ---------------------------------------------------------------------------
@branches_bp.route("/branches/<int:branch_id>/assets", methods=["GET"])
@require_org
def branch_assets(branch_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id FROM branches WHERE id = %s AND org_id = %s",
            (branch_id, org_id),
        )
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "Branch not found"}), 404

        cursor.execute(
            """SELECT a.*, c.name AS category_name
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.branch_id = %s AND a.org_id = %s AND a.status != 'disposed'
               ORDER BY a.name""",
            (branch_id, org_id),
        )
        assets = [_row(r) for r in cursor.fetchall()]
        return jsonify({"success": True, "assets": assets, "count": len(assets)}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /branches/<id>/summary
# ---------------------------------------------------------------------------
@branches_bp.route("/branches/<int:branch_id>/summary", methods=["GET"])
@require_org
def branch_summary(branch_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM branches WHERE id = %s AND org_id = %s",
            (branch_id, org_id),
        )
        branch = cursor.fetchone()
        if not branch:
            return jsonify({"success": False, "error": "Branch not found"}), 404

        # Financial summary
        cursor.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN type='income'  THEN amount ELSE 0 END), 0) AS total_income,
                 COALESCE(SUM(CASE WHEN type='expense' THEN amount ELSE 0 END), 0) AS total_expense,
                 COUNT(*) AS transaction_count
               FROM transactions
               WHERE branch_id = %s AND org_id = %s""",
            (branch_id, org_id),
        )
        fin = cursor.fetchone()

        # Asset summary
        cursor.execute(
            """SELECT
                 COUNT(*) AS total_assets,
                 COALESCE(SUM(purchase_price), 0) AS total_purchase_value,
                 COALESCE(SUM(current_value), 0) AS total_current_value,
                 SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active_assets,
                 SUM(CASE WHEN status='maintenance' THEN 1 ELSE 0 END) AS maintenance_assets
               FROM assets
               WHERE branch_id = %s AND org_id = %s AND status != 'disposed'""",
            (branch_id, org_id),
        )
        ast = cursor.fetchone()

        total_income = float(fin["total_income"])
        total_expense = float(fin["total_expense"])

        return jsonify({
            "success": True,
            "branch": {"id": branch["id"], "name": branch["name"]},
            "finance": {
                "total_income": total_income,
                "total_expense": total_expense,
                "net": round(total_income - total_expense, 2),
                "transaction_count": fin["transaction_count"],
            },
            "assets": {
                "total_assets": ast["total_assets"],
                "total_purchase_value": float(ast["total_purchase_value"]),
                "total_current_value": float(ast["total_current_value"]),
                "active_assets": ast["active_assets"],
                "maintenance_assets": ast["maintenance_assets"],
            },
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /assets/<asset_id>/transfer  — transfer asset between branches
# ---------------------------------------------------------------------------
@branches_bp.route("/assets/<int:asset_id>/transfer", methods=["POST"])
@require_org
def transfer_asset(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = claims.get("user_id")

    err = _require_admin_or_manager(claims)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    new_branch_id = data.get("branch_id")
    notes = data.get("notes", "Asset transferred between branches")

    if new_branch_id is None:
        return jsonify({"success": False, "error": "branch_id is required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Verify asset belongs to org
        cursor.execute(
            "SELECT id, branch_id, name FROM assets WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )
        asset = cursor.fetchone()
        if not asset:
            return jsonify({"success": False, "error": "Asset not found"}), 404

        # Verify destination branch belongs to org (or allow NULL to unassign)
        if new_branch_id is not None:
            cursor.execute(
                "SELECT id, name FROM branches WHERE id = %s AND org_id = %s AND is_active = TRUE",
                (new_branch_id, org_id),
            )
            if not cursor.fetchone():
                return jsonify({"success": False, "error": "Destination branch not found or inactive"}), 404

        old_branch_id = asset["branch_id"]

        cursor.execute(
            "UPDATE assets SET branch_id = %s WHERE id = %s AND org_id = %s",
            (new_branch_id, asset_id, org_id),
        )

        # Audit log in asset_history
        cursor.execute(
            """INSERT INTO asset_history
               (asset_id, changed_by, change_type, old_value, new_value, notes)
               VALUES (%s, %s, 'transfer', %s, %s, %s)""",
            (
                asset_id,
                user_id,
                json.dumps({"branch_id": old_branch_id}),
                json.dumps({"branch_id": new_branch_id}),
                notes,
            ),
        )
        
        # Also log to audit_logs table
        cursor.execute(
            """INSERT INTO audit_logs (user_id, org_id, action, details)
               VALUES (%s, %s, %s, %s)""",
            (
                user_id,
                org_id,
                "asset_transferred",
                json.dumps({
                    "asset_id": asset_id,
                    "from_branch_id": old_branch_id,
                    "to_branch_id": new_branch_id,
                    "notes": notes,
                }),
            ),
        )
        
        conn.commit()

        return jsonify({
            "success": True,
            "message": "Asset transferred successfully",
            "asset_id": asset_id,
            "from_branch_id": old_branch_id,
            "to_branch_id": new_branch_id,
        }), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
