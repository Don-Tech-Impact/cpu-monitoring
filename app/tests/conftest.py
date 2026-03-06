"""
Pytest configuration — mocks Redis and disables Flask-Limiter for all
tests so no live Redis or DB connection is required.
"""
import os
import sys
from unittest.mock import MagicMock, patch

# ── 1. Add app dir to path ────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 2. Set environment variables BEFORE any app import ───────────────────
os.environ["JWT_SECRET_KEY"]    = "supersecretkey-for-testing-only-32chars"
os.environ["REDIS_URL"]         = "redis://localhost:6380/0"
os.environ["DB_HOST"]           = "localhost"
os.environ["DB_NAME"]           = "testdb"
os.environ["DB_USER"]           = "root"
os.environ["DB_PASSWORD"]       = "root"
os.environ["FLASK_ENV"]         = "testing"

# ── 3. Build a mock Redis client ──────────────────────────────────────────
_mock_redis = MagicMock()
_mock_redis.get.return_value    = None   # no token is blocklisted
_mock_redis.setex.return_value  = True
_mock_redis.set.return_value    = True
_mock_redis.delete.return_value = 1
_mock_redis.ping.return_value   = True
_mock_redis.exists.return_value = 0

# ── 4. Patch redis.from_url AND _init_redis before app is imported ────────
#    This prevents any actual TCP connection attempt to Redis.
_from_url_patch = patch("redis.from_url",      return_value=_mock_redis)
_redis_cls_patch = patch("redis.Redis",        return_value=_mock_redis)
_strict_patch    = patch("redis.StrictRedis",  return_value=_mock_redis)

_from_url_patch.start()
_redis_cls_patch.start()
_strict_patch.start()

# ── 5. Also patch _init_redis in app module so create_app() gets the mock ─
#    We must import app AFTER the patches above are active.
import app as _app_module  # noqa: E402  (must be after patches)

# Monkey-patch _init_redis so it always returns the mock
_app_module._init_redis = lambda: _mock_redis

# Re-run create_app so the global redis_client gets the mock
# (the app singleton is already created at bottom of app.py — just
#  update the global reference directly)
_app_module.redis_client = _mock_redis

# ── 6. Disable Flask-Limiter ──────────────────────────────────────────────
_app_module.limiter.enabled = False
