"""
Assets blueprint
All routes require a valid JWT.  org_id is extracted from the token to enforce
multi-tenant isolation.

Routes:
  GET    /api/assets                    — list assets (filters: status, category_id)
  POST   /api/assets                    — create asset + audit log
  GET    /api/assets/export/csv         — CSV export (must be before /<id> routes)
  GET    /api/assets/<id>               — single asset with category name
  PUT    /api/assets/<id>               — update asset + audit log
  DELETE /api/assets/<id>               — soft-delete (status=disposed) + audit log
  GET    /api/assets/<id>/history       — full audit trail
  POST   /api/assets/<id>/maintenance   — log maintenance record

  GET    /api/asset-categories          — list categories for org
  POST   /api/asset-categories          — create category
"""

import csv
import io
import json
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from app import database_connection

assets_bp = Blueprint("assets", __name__)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _serial(obj):
    """JSON-serialise types that are not natively serialisable."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serialisable")


def _row(row: dict) -> dict:
    """Recursively convert a DB row dict so it is JSON-safe."""
    return {k: (_serial(v) if isinstance(v, (date, datetime, Decimal)) else v)
            for k, v in row.items()}


# ---------------------------------------------------------------------------
# GET /api/assets
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets", methods=["GET"])
@jwt_required()
def list_assets():
    claims = get_jwt()
    org_id = claims.get("org_id")

    status_filter = request.args.get("status")
    category_filter = request.args.get("category_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT a.*, c.name AS category_name
            FROM assets a
            LEFT JOIN asset_categories c ON c.id = a.category_id
            WHERE a.org_id = %s
        """
        params = [org_id]

        if status_filter:
            query += " AND a.status = %s"
            params.append(status_filter)
        if category_filter:
            query += " AND a.category_id = %s"
            params.append(category_filter)

        query += " ORDER BY a.created_at DESC"
        cursor.execute(query, params)
        assets = [_row(r) for r in cursor.fetchall()]
        return jsonify({"assets": assets, "count": len(assets)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/assets
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets", methods=["POST"])
@jwt_required()
def create_asset():
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = claims.get("user_id")

    data = request.get_json(silent=True) or {}

    required = ["asset_tag", "name"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Check asset_tag uniqueness within org
        cursor.execute(
            "SELECT id FROM assets WHERE org_id = %s AND asset_tag = %s",
            (org_id, data["asset_tag"]),
        )
        if cursor.fetchone():
            return jsonify({"error": "Asset tag already exists in this organisation"}), 409

        cursor.execute(
            """INSERT INTO assets
               (org_id, category_id, asset_tag, name, description, location,
                assigned_to, status, purchase_date, purchase_price, current_value,
                depreciation_rate, warranty_expiry, serial_number, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                org_id,
                data.get("category_id"),
                data["asset_tag"],
                data["name"],
                data.get("description"),
                data.get("location"),
                data.get("assigned_to"),
                data.get("status", "active"),
                data.get("purchase_date"),
                data.get("purchase_price"),
                data.get("current_value"),
                data.get("depreciation_rate", 0),
                data.get("warranty_expiry"),
                data.get("serial_number"),
                data.get("notes"),
            ),
        )
        asset_id = cursor.lastrowid

        # Audit log
        cursor.execute(
            """INSERT INTO asset_history
               (asset_id, changed_by, change_type, old_value, new_value, notes)
               VALUES (%s, %s, 'created', NULL, %s, %s)""",
            (asset_id, user_id, json.dumps(data, default=str), "Asset created"),
        )
        conn.commit()

        # Fetch created asset
        cursor.execute(
            """SELECT a.*, c.name AS category_name
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.id = %s""",
            (asset_id,),
        )
        asset = _row(cursor.fetchone())
        return jsonify({"message": "Asset created", "asset": asset}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/assets/export/csv  (must be declared BEFORE /<id> routes)
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/export/csv", methods=["GET"])
@jwt_required()
def export_assets_csv():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT a.id, a.asset_tag, a.name, c.name AS category,
                      a.location, a.assigned_to, a.status,
                      a.purchase_date, a.purchase_price, a.current_value,
                      a.depreciation_rate, a.warranty_expiry,
                      a.serial_number, a.description, a.notes,
                      a.created_at, a.updated_at
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.org_id = %s
               ORDER BY a.created_at DESC""",
            (org_id,),
        )
        rows = cursor.fetchall()

        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow({k: (v.isoformat() if isinstance(v, (date, datetime))
                                     else (float(v) if isinstance(v, Decimal) else v))
                                 for k, v in row.items()})
        else:
            output.write("No assets found\n")

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=assets.csv"},
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/assets/<id>
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/<int:asset_id>", methods=["GET"])
@jwt_required()
def get_asset(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT a.*, c.name AS category_name
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.id = %s AND a.org_id = %s""",
            (asset_id, org_id),
        )
        asset = cursor.fetchone()
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        return jsonify({"asset": _row(asset)}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /api/assets/<id>
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/<int:asset_id>", methods=["PUT"])
@jwt_required()
def update_asset(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = identity["user_id"]

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "No data provided"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Fetch existing asset
        cursor.execute(
            "SELECT * FROM assets WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Asset not found"}), 404

        # Build dynamic UPDATE
        allowed_fields = [
            "category_id", "asset_tag", "name", "description", "location",
            "assigned_to", "status", "purchase_date", "purchase_price",
            "current_value", "depreciation_rate", "warranty_expiry",
            "serial_number", "notes",
        ]
        updates = {k: v for k, v in data.items() if k in allowed_fields}
        if not updates:
            return jsonify({"error": "No valid fields to update"}), 400

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [asset_id, org_id]
        cursor.execute(
            f"UPDATE assets SET {set_clause} WHERE id = %s AND org_id = %s",
            values,
        )

        # Audit log
        old_val = {k: (_serial(v) if isinstance(v, (date, datetime, Decimal)) else v)
                   for k, v in existing.items()}
        cursor.execute(
            """INSERT INTO asset_history
               (asset_id, changed_by, change_type, old_value, new_value, notes)
               VALUES (%s, %s, 'updated', %s, %s, %s)""",
            (
                asset_id,
                user_id,
                json.dumps(old_val),
                json.dumps(updates, default=str),
                data.get("notes", "Asset updated"),
            ),
        )
        conn.commit()

        # Return updated asset
        cursor.execute(
            """SELECT a.*, c.name AS category_name
               FROM assets a
               LEFT JOIN asset_categories c ON c.id = a.category_id
               WHERE a.id = %s""",
            (asset_id,),
        )
        asset = _row(cursor.fetchone())
        return jsonify({"message": "Asset updated", "asset": asset}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# DELETE /api/assets/<id>  — soft delete (status = 'disposed')
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/<int:asset_id>", methods=["DELETE"])
@jwt_required()
def delete_asset(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = identity["user_id"]

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM assets WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Asset not found"}), 404

        cursor.execute(
            "UPDATE assets SET status = 'disposed' WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )

        old_val = {k: (_serial(v) if isinstance(v, (date, datetime, Decimal)) else v)
                   for k, v in existing.items()}
        cursor.execute(
            """INSERT INTO asset_history
               (asset_id, changed_by, change_type, old_value, new_value, notes)
               VALUES (%s, %s, 'disposed', %s, %s, %s)""",
            (
                asset_id,
                user_id,
                json.dumps(old_val),
                json.dumps({"status": "disposed"}),
                "Asset marked as disposed",
            ),
        )
        conn.commit()
        return jsonify({"message": "Asset marked as disposed"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/assets/<id>/history
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/<int:asset_id>/history", methods=["GET"])
@jwt_required()
def asset_history(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Verify asset belongs to org
        cursor.execute(
            "SELECT id FROM assets WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Asset not found"}), 404

        cursor.execute(
            """SELECT h.*, u.name AS changed_by_name
               FROM asset_history h
               LEFT JOIN users u ON u.id = h.changed_by
               WHERE h.asset_id = %s
               ORDER BY h.changed_at DESC""",
            (asset_id,),
        )
        history = []
        for row in cursor.fetchall():
            r = dict(row)
            r["changed_at"] = r["changed_at"].isoformat() if r.get("changed_at") else None
            # old_value / new_value come back as str or dict depending on driver
            for field in ("old_value", "new_value"):
                if isinstance(r.get(field), str):
                    try:
                        r[field] = json.loads(r[field])
                    except (ValueError, TypeError):
                        pass
            history.append(r)

        return jsonify({"asset_id": asset_id, "history": history}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/assets/<id>/maintenance
# ---------------------------------------------------------------------------
@assets_bp.route("/api/assets/<int:asset_id>/maintenance", methods=["POST"])
@jwt_required()
def log_maintenance(asset_id):
    claims = get_jwt()
    org_id = claims.get("org_id")
    user_id = identity["user_id"]

    data = request.get_json(silent=True) or {}

    if not data.get("maintenance_date"):
        return jsonify({"error": "maintenance_date is required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Verify asset belongs to org
        cursor.execute(
            "SELECT id FROM assets WHERE id = %s AND org_id = %s",
            (asset_id, org_id),
        )
        if not cursor.fetchone():
            return jsonify({"error": "Asset not found"}), 404

        cursor.execute(
            """INSERT INTO maintenance_records
               (asset_id, org_id, maintenance_date, cost, performed_by,
                description, next_due_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                asset_id,
                org_id,
                data["maintenance_date"],
                data.get("cost"),
                data.get("performed_by"),
                data.get("description"),
                data.get("next_due_date"),
            ),
        )
        record_id = cursor.lastrowid

        # Update asset status to 'maintenance' if requested
        if data.get("update_status", False):
            cursor.execute(
                "UPDATE assets SET status = 'maintenance' WHERE id = %s AND org_id = %s",
                (asset_id, org_id),
            )

        # Audit log
        cursor.execute(
            """INSERT INTO asset_history
               (asset_id, changed_by, change_type, old_value, new_value, notes)
               VALUES (%s, %s, 'maintenance', NULL, %s, %s)""",
            (
                asset_id,
                user_id,
                json.dumps(data, default=str),
                data.get("description", "Maintenance logged"),
            ),
        )
        conn.commit()

        return jsonify({
            "message": "Maintenance record created",
            "record_id": record_id,
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/asset-categories
# ---------------------------------------------------------------------------
@assets_bp.route("/api/asset-categories", methods=["GET"])
@jwt_required()
def list_categories():
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM asset_categories WHERE org_id = %s ORDER BY name",
            (org_id,),
        )
        categories = cursor.fetchall()
        return jsonify({"categories": categories}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/asset-categories
# ---------------------------------------------------------------------------
@assets_bp.route("/api/asset-categories", methods=["POST"])
@jwt_required()
def create_category():
    claims = get_jwt()
    org_id = claims.get("org_id")

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO asset_categories (org_id, name) VALUES (%s, %s)",
            (org_id, name),
        )
        cat_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "message": "Category created",
            "category": {"id": cat_id, "org_id": org_id, "name": name},
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
