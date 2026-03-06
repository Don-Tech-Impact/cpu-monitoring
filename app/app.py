"""
Finance & Asset Tracking SaaS — Application Factory
"""

import os
import time
from datetime import timedelta
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt, get_jwt_identity, verify_jwt_in_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

try:
    from prometheus_flask_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    Instrumentator = None

try:
    import redis as redis_lib
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

load_dotenv()

# ---------------------------------------------------------------------------
# Extensions — initialised without app so blueprints can import them
# ---------------------------------------------------------------------------
bcrypt = Bcrypt()
jwt = JWTManager()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=REDIS_URL,
    default_limits=["200 per hour"],
    strategy="fixed-window",
)

# Redis client for refresh token storage — lazily created inside create_app
# so test patches applied before import take effect correctly.
redis_client = None


def _init_redis():
    """Attempt to create a Redis client; return None on failure."""
    if not HAS_REDIS:
        return None
    try:
        client = redis_lib.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        client.ping()  # fail fast if Redis is unreachable
        return client
    except Exception as e:
        print(f"[Redis] Connection warning: {e}")
        return None


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------
def database_connection():
    """Return a MySQL connection with retry logic (up to 5 attempts)."""
    retries = 5
    while retries > 0:
        try:
            connection = mysql.connector.connect(
                host=os.getenv("DB_HOST", "localhost"),
                user=os.getenv("DB_USER", "finance_user"),
                password=os.getenv("DB_PASSWORD", ""),
                database=os.getenv("DB_NAME", "finance_db"),
            )
            return connection
        except mysql.connector.Error as err:
            print(f"[DB] Connection error: {err}")
            retries -= 1
            time.sleep(2)
    return None


# ---------------------------------------------------------------------------
# require_org decorator
# ---------------------------------------------------------------------------
def require_org(f):
    """
    Decorator: validates JWT, ensures org_id claim is present, and blocks
    access if must_change_password is set (force-change-password flow).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        if not claims.get("org_id"):
            return jsonify({"success": False, "error": "Invalid token: missing org_id"}), 401
        # Enforce forced password change — block all non-auth routes
        if claims.get("must_change_password"):
            return jsonify({
                "success": False,
                "error": "Password change required before accessing this resource",
                "must_change_password": True,
            }), 403
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app():
    app = Flask(__name__, template_folder="templates")

    # ------------------------------------------------------------------
    # JWT configuration
    # ------------------------------------------------------------------
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if not jwt_secret or jwt_secret in ("change-me-in-production", "changeme"):
        import warnings
        warnings.warn(
            "[SECURITY] JWT_SECRET_KEY is not set or uses default value. "
            "Set a strong secret in your .env file.",
            stacklevel=2,
        )
        if os.getenv("FLASK_ENV", "development") == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a strong value in production."
            )

    app.config["JWT_SECRET_KEY"] = jwt_secret or "dev-only-insecure-key"
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRY_MINUTES", "15"))
    )
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRY_DAYS", "7"))
    )
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["FLASK_ENV"] = os.getenv("FLASK_ENV", "development")

    # ------------------------------------------------------------------
    # CORS — restrict to known origins
    # ------------------------------------------------------------------
    cors_origins_raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5000,http://localhost:80",
    )
    cors_origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
    CORS(app, origins=cors_origins, supports_credentials=True)

    # ------------------------------------------------------------------
    # Initialise extensions
    # ------------------------------------------------------------------
    bcrypt.init_app(app)
    # Explicitly set bcrypt cost factor (min 12 per security requirements)
    app.config["BCRYPT_LOG_ROUNDS"] = int(os.getenv("BCRYPT_LOG_ROUNDS", "12"))
    jwt.init_app(app)

    # Disable rate limiting in TESTING mode before limiter.init_app()
    if app.config.get("TESTING"):
        app.config["RATELIMIT_ENABLED"] = False

    limiter.init_app(app)

    # Initialise Redis lazily (after patches are in place during tests)
    global redis_client
    redis_client = _init_redis()

    # ------------------------------------------------------------------
    # Security headers — applied to every response
    # ------------------------------------------------------------------
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        if os.getenv("FLASK_ENV") == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response

    # ------------------------------------------------------------------
    # Prometheus metrics (optional)
    # ------------------------------------------------------------------
    if HAS_PROMETHEUS and Instrumentator:
        Instrumentator().instrument(app).expose(app)

    # ------------------------------------------------------------------
    # Register blueprints — all under /api/v1/
    # ------------------------------------------------------------------
    from blueprints.auth import auth_bp
    from blueprints.assets import assets_bp
    from blueprints.finance import finance_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.settings import settings_bp
    from blueprints.bank_accounts import bank_accounts_bp
    from blueprints.superadmin import superadmin_bp
    from blueprints.team import team_bp
    from blueprints.branches import branches_bp
    from blueprints.reports import reports_bp

    app.register_blueprint(auth_bp,         url_prefix="/api/v1/auth")
    app.register_blueprint(assets_bp,       url_prefix="/api/v1")
    app.register_blueprint(finance_bp,      url_prefix="/api/v1")
    app.register_blueprint(dashboard_bp,    url_prefix="/api/v1")
    app.register_blueprint(settings_bp,     url_prefix="/api/v1")
    app.register_blueprint(bank_accounts_bp, url_prefix="/api/v1")
    app.register_blueprint(superadmin_bp,   url_prefix="/api/v1/superadmin")
    app.register_blueprint(team_bp,         url_prefix="/api/v1")
    app.register_blueprint(branches_bp,     url_prefix="/api/v1")
    app.register_blueprint(reports_bp,      url_prefix="/api/v1")

    # ------------------------------------------------------------------
    # Health check — GET /health
    # ------------------------------------------------------------------
    @app.route("/health")
    def health():
        db_ok = False
        redis_ok = False

        conn = database_connection()
        if conn:
            db_ok = True
            conn.close()

        if redis_client:
            try:
                redis_client.ping()
                redis_ok = True
            except Exception:
                pass

        status = "healthy" if (db_ok and redis_ok) else "degraded"
        code = 200 if status == "healthy" else 503
        return jsonify({
            "status": status,
            "database": "connected" if db_ok else "unavailable",
            "redis": "connected" if redis_ok else "unavailable",
        }), code

    # ------------------------------------------------------------------
    # Root route & UI route — serves the single-page frontend
    # ------------------------------------------------------------------
    @app.route("/")
    @app.route("/login")
    @app.route("/login/")
    def ui():
        return render_template("index.html")
    
    # ------------------------------------------------------------------
    # API info route
    # ------------------------------------------------------------------
    @app.route("/api")
    @app.route("/api/")
    def index():
        return jsonify({
            "name": "Finance & Asset Tracking SaaS API",
            "version": "1.0.0",
            "status": "running",
            "docs": "See /health for service status",
            "api_base": "/api/v1",
            "endpoints": {
                "auth":        "/api/v1/auth",
                "assets":      "/api/v1/assets",
                "finance":     "/api/v1/finance",
                "branches":    "/api/v1/branches",
                "reports":     "/api/v1/reports",
                "dashboard":   "/api/v1/dashboard",
                "settings":    "/api/v1/settings",
                "team":        "/api/v1/team",
                "superadmin":  "/api/v1/superadmin",
                "health":      "/health",
                "ui":          "/login",
            },
        })

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
