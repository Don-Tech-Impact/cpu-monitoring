"""
Authentication blueprint
Routes:
  POST /api/auth/register  — create org + admin user, return JWT
  POST /api/auth/login     — validate credentials, return JWT
  GET  /api/auth/me        — return current user info (JWT required)
"""

import re
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, jwt_required

from app import bcrypt, database_connection

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert org name to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50]


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    # Validate required fields
    required = ["org_name", "name", "email", "password"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    org_name = data["org_name"].strip()
    name = data["name"].strip()
    email = data["email"].strip().lower()
    password = data["password"]

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    slug = _slugify(org_name)
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # Check email uniqueness
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"error": "Email already registered"}), 409

        # Check slug uniqueness — append random suffix if taken
        cursor.execute("SELECT id FROM organizations WHERE slug = %s", (slug,))
        if cursor.fetchone():
            import random, string
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            slug = f"{slug}-{suffix}"

        # Create organization
        cursor.execute(
            "INSERT INTO organizations (name, slug, plan) VALUES (%s, %s, 'free')",
            (org_name, slug),
        )
        org_id = cursor.lastrowid

        # Create admin user
        cursor.execute(
            """INSERT INTO users (org_id, name, email, password_hash, role)
               VALUES (%s, %s, %s, %s, 'admin')""",
            (org_id, name, email, password_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()

        identity = {"user_id": user_id, "org_id": org_id, "role": "admin"}
        access_token = create_access_token(identity=identity)

        return jsonify({
            "message": "Registration successful",
            "access_token": access_token,
            "user": {
                "id": user_id,
                "name": name,
                "email": email,
                "role": "admin",
                "org_id": org_id,
                "org_name": org_name,
                "org_slug": slug,
            },
        }), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.id, u.org_id, u.name, u.email, u.password_hash, u.role,
                      o.name AS org_name, o.slug AS org_slug, o.plan
               FROM users u
               JOIN organizations o ON o.id = u.org_id
               WHERE u.email = %s""",
            (email,),
        )
        user = cursor.fetchone()

        if not user or not bcrypt.check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        identity = str(user["id"])
        access_token = create_access_token(
            identity=identity,
            additional_claims={
                "user_id": user["id"],
                "org_id": user["org_id"],
                "role": user["role"],
            }
        )

        return jsonify({
            "message": "Login successful",
            "access_token": access_token,
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
                "org_id": user["org_id"],
                "org_name": user["org_name"],
                "org_slug": user["org_slug"],
                "plan": user["plan"],
            },
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    identity = get_jwt_identity()
    user_id = int(identity)
    claims = get_jwt()
    org_id = claims.get("org_id")
    role = claims.get("role")
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.id, u.org_id, u.name, u.email, u.role, u.created_at,
                      o.name AS org_name, o.slug AS org_slug, o.plan
               FROM users u
               JOIN organizations o ON o.id = u.org_id
               WHERE u.id = %s AND u.org_id = %s""",
            (user_id, org_id),
        )
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Serialize datetime
        user["created_at"] = user["created_at"].isoformat() if user.get("created_at") else None

        return jsonify({"user": user}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
