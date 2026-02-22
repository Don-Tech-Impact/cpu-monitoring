import os
import time
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager, get_jwt_identity, verify_jwt_in_request
try:
    from prometheus_flask_instrumentator import Instrumentator
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    Instrumentator = None

load_dotenv()

# ---------------------------------------------------------------------------
# Extensions (initialised without app so blueprints can import them)
# ---------------------------------------------------------------------------
bcrypt = Bcrypt()
jwt = JWTManager()


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
                password=os.getenv("DB_PASSWORD", "finance_pass@2026"),
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
    """Decorator: validates JWT and injects org_id / user_id into kwargs."""
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        identity = get_jwt_identity()
        if not identity or "org_id" not in identity:
            return jsonify({"error": "Invalid token identity"}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app():
    app = Flask(__name__, template_folder='templates')

    # JWT configuration
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", os.getenv("app_secret", "change-me-in-production"))
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 86400  # 24 hours in seconds

    # Initialise extensions
    bcrypt.init_app(app)
    jwt.init_app(app)
    CORS(app)

    # Prometheus metrics at /metrics (optional)
    if HAS_PROMETHEUS and Instrumentator:
        Instrumentator().instrument(app).expose(app)

    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.assets import assets_bp
    from blueprints.finance import finance_bp
    from blueprints.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(dashboard_bp)

    # ------------------------------------------------------------------
    # Root route
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        return jsonify({
            "name": "SmallBiz Asset & Finance Manager API",
            "version": "1.0.0",
            "status": "running",
            "database": "connected" if database_connection() else "unavailable",
            "endpoints": {
                "auth": [
                    "POST /api/auth/register",
                    "POST /api/auth/login",
                    "GET  /api/auth/me",
                ],
                "assets": [
                    "GET    /api/assets",
                    "POST   /api/assets",
                    "GET    /api/assets/<id>",
                    "PUT    /api/assets/<id>",
                    "DELETE /api/assets/<id>",
                    "GET    /api/assets/<id>/history",
                    "POST   /api/assets/<id>/maintenance",
                    "GET    /api/assets/export/csv",
                    "GET    /api/asset-categories",
                    "POST   /api/asset-categories",
                ],
                "finance": [
                    "GET    /api/finance/transactions",
                    "POST   /api/finance/transactions",
                    "GET    /api/finance/transactions/<id>",
                    "PUT    /api/finance/transactions/<id>",
                    "DELETE /api/finance/transactions/<id>",
                    "GET    /api/finance/accounts",
                    "POST   /api/finance/accounts",
                    "GET    /api/finance/categories",
                    "POST   /api/finance/categories",
                    "GET    /api/finance/summary",
                    "GET    /api/finance/cashflow",
                    "GET    /api/finance/export/csv",
                ],
                "dashboard": [
                    "GET /api/dashboard",
                    "GET /health",
                ],
            },
        })

    # ------------------------------------------------------------------
    # UI route — serves the single-page frontend
    # ------------------------------------------------------------------
    @app.route('/ui')
    @app.route('/ui/')
    def ui():
        return render_template('index.html')

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
