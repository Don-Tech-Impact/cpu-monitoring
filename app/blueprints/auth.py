"""
Authentication blueprint
Routes (all prefixed with /api/v1/auth in app.py):
  POST /register          — create org + admin user, return JWT
  POST /login             — validate credentials, return JWT + set refresh cookie
  POST /refresh           — rotate refresh token, return new access token
  POST /logout            — invalidate refresh token, clear cookie
  POST /change-password   — force-change-password flow
  GET  /me                — return current user info (JWT required)
"""

import re
import secrets
import os
from datetime import timedelta

from flask import Blueprint, jsonify, make_response, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)

from app import bcrypt, database_connection, limiter, redis_client

auth_bp = Blueprint("auth", __name__)

_REFRESH_TTL = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRY_DAYS", "7")) * 24 * 3600
_IS_PRODUCTION = os.getenv("FLASK_ENV", "development") == "production"


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


def _validate_password_strength(password: str) -> str | None:
    """Return error message if password fails strength requirements, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return "Password must contain at least one digit"
    return None


def _set_refresh_cookie(response, refresh_token: str):
    """Attach the refresh token as an HTTP-only cookie."""
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="Lax",
        max_age=_REFRESH_TTL,
        path="/api/v1/auth",
    )
    return response


def _store_refresh_token(refresh_token: str, user_id: int):
    """Store refresh token in Redis with TTL."""
    if redis_client:
        redis_client.setex(f"refresh:{refresh_token}", _REFRESH_TTL, str(user_id))


def _delete_refresh_token(refresh_token: str):
    """Remove refresh token from Redis."""
    if redis_client:
        redis_client.delete(f"refresh:{refresh_token}")


def _build_jwt_claims(user: dict) -> dict:
    """Build additional JWT claims from a user DB row."""
    return {
        "user_id": user["id"],
        "org_id": user["org_id"],
        "role": user["role"],
        "is_superadmin": bool(user.get("is_superadmin", False)),
        "must_change_password": bool(user.get("must_change_password", False)),
        "branch_id": user.get("branch_id"),
    }


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------
@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    data = request.get_json(silent=True) or {}

    required = ["org_name", "name", "email", "password"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"success": False, "error": f"Missing required fields: {', '.join(missing)}"}), 400

    org_name = data["org_name"].strip()
    name = data["name"].strip()
    email = data["email"].strip().lower()
    password = data["password"]

    err = _validate_password_strength(password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    # Basic email format check
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"success": False, "error": "Invalid email format"}), 400

    slug = _slugify(org_name)
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "error": "Email already registered"}), 409

        cursor.execute("SELECT id FROM organizations WHERE slug = %s", (slug,))
        if cursor.fetchone():
            suffix = secrets.token_hex(2)
            slug = f"{slug}-{suffix}"

        cursor.execute(
            "INSERT INTO organizations (name, slug, plan) VALUES (%s, %s, 'free')",
            (org_name, slug),
        )
        org_id = cursor.lastrowid

        cursor.execute(
            """INSERT INTO users (org_id, name, email, password_hash, role, must_change_password)
               VALUES (%s, %s, %s, %s, 'admin', FALSE)""",
            (org_id, name, email, password_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()

        claims = {
            "user_id": user_id, "org_id": org_id, "role": "admin",
            "is_superadmin": False, "must_change_password": False, "branch_id": None,
        }
        access_token = create_access_token(identity=str(user_id), additional_claims=claims)
        refresh_token = create_refresh_token(identity=str(user_id), additional_claims=claims)
        _store_refresh_token(refresh_token, user_id)

        resp = make_response(jsonify({
            "success": True,
            "message": "Registration successful",
            "access_token": access_token,
            "user": {
                "id": user_id, "name": name, "email": email,
                "role": "admin", "org_id": org_id, "org_name": org_name,
                "org_slug": slug, "must_change_password": False,
            },
        }), 201)
        return _set_refresh_cookie(resp, refresh_token)

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------
@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.id, u.org_id, u.name, u.email, u.password_hash, u.role,
                      u.is_superadmin, u.must_change_password, u.branch_id, u.is_active,
                      o.name AS org_name, o.slug AS org_slug, o.plan
               FROM users u
               JOIN organizations o ON o.id = u.org_id
               WHERE u.email = %s""",
            (email,),
        )
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "error": "Invalid email or password"}), 401

        if not bcrypt.check_password_hash(user["password_hash"], password):
            return jsonify({"success": False, "error": "Invalid email or password"}), 401

        if not user.get("is_active", True):
            return jsonify({"success": False, "error": "Account is deactivated"}), 401

        # Block login if the organisation is suspended (unless superadmin)
        if not bool(user.get("is_superadmin", False)):
            cursor.execute(
                "SELECT is_active FROM organizations WHERE id = %s",
                (user["org_id"],),
            )
            org_row = cursor.fetchone()
            if org_row and not org_row.get("is_active", True):
                return jsonify({"success": False, "error": "Your organisation account has been suspended. Please contact support."}), 403

        # Log login in audit_logs
        try:
            cursor.execute(
                """INSERT INTO audit_logs (user_id, org_id, action, details, ip_address)
                   VALUES (%s, %s, 'login', 'User logged in', %s)""",
                (user["id"], user["org_id"], request.remote_addr),
            )
            conn.commit()
        except Exception:
            pass  # Don't fail login if audit log fails

        claims = _build_jwt_claims(user)
        access_token = create_access_token(identity=str(user["id"]), additional_claims=claims)
        refresh_token = create_refresh_token(identity=str(user["id"]), additional_claims=claims)
        _store_refresh_token(refresh_token, user["id"])

        resp = make_response(jsonify({
            "success": True,
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
                "is_superadmin": bool(user.get("is_superadmin", False)),
                "must_change_password": bool(user.get("must_change_password", False)),
                "branch_id": user.get("branch_id"),
            },
        }), 200)
        return _set_refresh_cookie(resp, refresh_token)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        conn.close()


# ---------------------------------------------------------------------------
# POST /refresh  — rotate refresh token
# ---------------------------------------------------------------------------
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    old_refresh_token = request.cookies.get("refresh_token")
    if not old_refresh_token:
        return jsonify({"success": False, "error": "Refresh token not found"}), 401

    # Validate against Redis
    if redis_client:
        user_id_str = redis_client.get(f"refresh:{old_refresh_token}")
        if not user_id_str:
            return jsonify({"success": False, "error": "Refresh token expired or invalid"}), 401
        user_id = int(user_id_str)
    else:
        # Fallback: decode JWT directly if Redis unavailable
        try:
            from flask_jwt_extended import decode_token
            decoded = decode_token(old_refresh_token)
            user_id = int(decoded["sub"])
        except Exception:
            return jsonify({"success": False, "error": "Invalid refresh token"}), 401

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.*, o.name AS org_name, o.slug AS org_slug, o.plan
               FROM users u JOIN organizations o ON o.id = u.org_id
               WHERE u.id = %s AND u.is_active = TRUE""",
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "error": "User not found or inactive"}), 401

        # Rotate: delete old, issue new
        _delete_refresh_token(old_refresh_token)

        claims = _build_jwt_claims(user)
        new_access_token = create_access_token(identity=str(user["id"]), additional_claims=claims)
        new_refresh_token = create_refresh_token(identity=str(user["id"]), additional_claims=claims)
        _store_refresh_token(new_refresh_token, user["id"])

        resp = make_response(jsonify({
            "success": True,
            "access_token": new_access_token,
        }), 200)
        return _set_refresh_cookie(resp, new_refresh_token)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /logout
# ---------------------------------------------------------------------------
@auth_bp.route("/logout", methods=["POST"])
def logout():
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        _delete_refresh_token(refresh_token)

    resp = make_response(jsonify({"success": True, "message": "Logged out successfully"}), 200)
    resp.set_cookie(
        "refresh_token", "", httponly=True, secure=_IS_PRODUCTION,
        samesite="Lax", max_age=0, path="/api/v1/auth",
    )
    return resp


# ---------------------------------------------------------------------------
# POST /change-password
# ---------------------------------------------------------------------------
@auth_bp.route("/change-password", methods=["POST"])
@jwt_required()
def change_password():
    identity = get_jwt_identity()
    claims = get_jwt()
    user_id = int(identity)
    org_id = claims.get("org_id")

    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not old_password or not new_password:
        return jsonify({"success": False, "error": "old_password and new_password are required"}), 400

    err = _validate_password_strength(new_password)
    if err:
        return jsonify({"success": False, "error": err}), 400

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, password_hash FROM users WHERE id = %s AND org_id = %s",
            (user_id, org_id),
        )
        user = cursor.fetchone()
        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        if not bcrypt.check_password_hash(user["password_hash"], old_password):
            return jsonify({"success": False, "error": "Current password is incorrect"}), 401

        if old_password == new_password:
            return jsonify({"success": False, "error": "New password must differ from current password"}), 400

        new_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
        cursor.execute(
            "UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
            (new_hash, user_id),
        )

        # Audit log
        cursor.execute(
            """INSERT INTO audit_logs (user_id, org_id, action, details, ip_address)
               VALUES (%s, %s, 'password_change', 'Password changed successfully', %s)""",
            (user_id, org_id, request.remote_addr),
        )
        conn.commit()

        return jsonify({"success": True, "message": "Password changed successfully"}), 200

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    identity = get_jwt_identity()
    user_id = int(identity)
    claims = get_jwt()
    org_id = claims.get("org_id")

    conn = database_connection()
    if not conn:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT u.id, u.org_id, u.name, u.email, u.role, u.is_superadmin,
                      u.must_change_password, u.branch_id, u.created_at,
                      o.name AS org_name, o.slug AS org_slug, o.plan
               FROM users u
               JOIN organizations o ON o.id = u.org_id
               WHERE u.id = %s AND u.org_id = %s""",
            (user_id, org_id),
        )
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "error": "User not found"}), 404

        user["created_at"] = user["created_at"].isoformat() if user.get("created_at") else None
        user["is_superadmin"] = bool(user.get("is_superadmin"))
        user["must_change_password"] = bool(user.get("must_change_password"))

        return jsonify({"success": True, "user": user}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
