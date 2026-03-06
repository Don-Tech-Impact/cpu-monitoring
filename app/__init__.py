"""
App package exports.

This file allows other modules (e.g., blueprints) to import from the app package:
    from app import database_connection, require_org, bcrypt, ...

The Flask application object is exposed as 'app'.
"""

# Import the application object and all necessary components from app.py
from app.app import (
    create_app,
    database_connection,
    require_org,
    bcrypt,
    limiter,
    redis_client,
)

# Expose the app object for gunicorn
# This allows: gunicorn "app:app"
app = create_app()

__all__ = [
    "app",
    "create_app",
    "database_connection",
    "require_org",
    "bcrypt",
    "limiter",
    "redis_client",
]
