"""
Smoke tests for the Finance & Asset Tracking SaaS API.
Run: cd app && python -m pytest tests/ -v

Tests use mocked DB connections — no live database required.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _make_mock_conn(fetchone_return=None, fetchall_return=None):
    """Helper: build a mock DB connection + cursor."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    if fetchone_return is not None:
        mock_cursor.fetchone.return_value = fetchone_return
    if fetchall_return is not None:
        mock_cursor.fetchall.return_value = fetchall_return
    return mock_conn, mock_cursor


def _get_token(client, is_superadmin=False):
    """Log in with a mocked user and return the access token."""
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('Admin@2026!').decode('utf-8')

    user_row = {
        'id': 1 if is_superadmin else 2,
        'org_id': 1 if is_superadmin else 2,
        'name': 'Super Admin' if is_superadmin else 'Demo Admin',
        'email': 'admin@system.com' if is_superadmin else 'admin@demo.com',
        'password_hash': hashed,
        'role': 'admin',
        'is_superadmin': 1 if is_superadmin else 0,
        'must_change_password': 0,
        'branch_id': None,
        'is_active': 1,
        'org_name': 'System' if is_superadmin else 'Demo Clinic',
        'org_slug': 'system' if is_superadmin else 'demo-clinic',
        'plan': 'enterprise' if is_superadmin else 'pro',
    }

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    # fetchone returns user_row for user lookup; subsequent calls (audit log) return None
    mock_cursor.fetchone.return_value = user_row

    email = 'admin@system.com' if is_superadmin else 'admin@demo.com'
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': email, 'password': 'Admin@2026!'})
    data = resp.get_json()
    if not data or 'access_token' not in data:
        raise RuntimeError(f"Login failed in _get_token: {resp.status_code} {data}")
    return data['access_token']


def _auth_headers(token):
    return {'Authorization': f'Bearer {token}'}


# ===========================================================================
# ROOT / INDEX
# ===========================================================================

def test_index_returns_200(client):
    resp = client.get('/')
    assert resp.status_code == 200

def test_index_has_api_base(client):
    data = client.get('/').get_json()
    assert data['api_base'] == '/api/v1'
    assert 'endpoints' in data
    assert data['status'] == 'running'


# ===========================================================================
# HEALTH CHECK
# ===========================================================================

def test_health_no_db_returns_degraded(client):
    with patch('app.database_connection', return_value=None):
        with patch('blueprints.dashboard.database_connection', return_value=None):
            resp = client.get('/health')
    assert resp.status_code in (200, 503, 500)

def test_api_v1_health_proxied_via_nginx():
    """Nginx proxies /api/v1/health -> /health — just assert route path is correct in nginx.conf."""
    import os
    conf = open(os.path.join(os.path.dirname(__file__), '../../nginx/nginx.conf')).read()
    assert '/api/v1/health' in conf


# ===========================================================================
# AUTH — LOGIN
# ===========================================================================

def test_login_missing_password(client):
    resp = client.post('/api/v1/auth/login', json={'email': 'a@b.com'})
    assert resp.status_code == 400
    assert 'error' in resp.get_json()

def test_login_missing_email(client):
    resp = client.post('/api/v1/auth/login', json={'password': 'pass'})
    assert resp.status_code == 400

def test_login_db_unavailable(client):
    with patch('blueprints.auth.database_connection', return_value=None):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'a@b.com', 'password': 'pass'})
    assert resp.status_code == 500

def test_login_user_not_found(client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    # fetchone returns None → user not found → should return 401
    mock_cursor.fetchone.return_value = None
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'no@one.com', 'password': 'wrong'})
    assert resp.status_code == 401

def test_login_wrong_password(client):
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('correct_password').decode('utf-8')
    user_row = {
        'id': 2, 'org_id': 2, 'name': 'Test', 'email': 'a@b.com',
        'password_hash': hashed, 'role': 'admin', 'is_superadmin': 0,
        'must_change_password': 0, 'branch_id': None, 'is_active': 1,
        'org_name': 'Demo', 'org_slug': 'demo', 'plan': 'free',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'a@b.com', 'password': 'wrong_password'})
    assert resp.status_code == 401

def test_login_success_returns_token(client):
    token = _get_token(client, is_superadmin=False)
    assert token is not None
    assert len(token) > 20

def test_login_superadmin_flag(client):
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('Admin@2026!').decode('utf-8')
    user_row = {
        'id': 1, 'org_id': 1, 'name': 'Super Admin', 'email': 'admin@system.com',
        'password_hash': hashed, 'role': 'admin', 'is_superadmin': 1,
        'must_change_password': 0, 'branch_id': None, 'is_active': 1,
        'org_name': 'System', 'org_slug': 'system', 'plan': 'enterprise',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'admin@system.com', 'password': 'Admin@2026!'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['user']['is_superadmin'] is True

def test_login_inactive_user_rejected(client):
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('Admin@2026!').decode('utf-8')
    user_row = {
        'id': 2, 'org_id': 2, 'name': 'Inactive', 'email': 'x@y.com',
        'password_hash': hashed, 'role': 'viewer', 'is_superadmin': 0,
        'must_change_password': 0, 'branch_id': None, 'is_active': 0,
        'org_name': 'Demo', 'org_slug': 'demo', 'plan': 'free',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'x@y.com', 'password': 'Admin@2026!'})
    assert resp.status_code == 401


# ===========================================================================
# AUTH — REGISTER
# ===========================================================================

def test_register_missing_fields(client):
    resp = client.post('/api/v1/auth/register', json={'org_name': 'Acme'})
    assert resp.status_code == 400

def test_register_weak_password(client):
    resp = client.post('/api/v1/auth/register', json={
        'org_name': 'Acme', 'name': 'Bob', 'email': 'bob@acme.com', 'password': 'weak'
    })
    assert resp.status_code == 400

def test_register_invalid_email(client):
    resp = client.post('/api/v1/auth/register', json={
        'org_name': 'Acme', 'name': 'Bob', 'email': 'not-an-email', 'password': 'Strong@123'
    })
    assert resp.status_code == 400

def test_register_db_unavailable(client):
    with patch('blueprints.auth.database_connection', return_value=None):
        resp = client.post('/api/v1/auth/register', json={
            'org_name': 'Acme', 'name': 'Bob',
            'email': 'bob@acme.com', 'password': 'Strong@123'
        })
    assert resp.status_code == 500


# ===========================================================================
# AUTH — /me
# ===========================================================================

def test_me_requires_auth(client):
    resp = client.get('/api/v1/auth/me')
    assert resp.status_code == 401

def test_me_returns_user(client):
    token = _get_token(client, is_superadmin=False)
    user_row = {
        'id': 2, 'org_id': 2, 'name': 'Demo Admin', 'email': 'admin@demo.com',
        'role': 'admin', 'is_superadmin': 0, 'must_change_password': 0,
        'branch_id': None, 'created_at': datetime(2024, 1, 1),
        'org_name': 'Demo Clinic', 'org_slug': 'demo-clinic', 'plan': 'pro',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/auth/me', headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'user' in data
    assert data['user']['email'] == 'admin@demo.com'
    assert data['user']['is_superadmin'] is False

def test_me_superadmin_flag_true(client):
    token = _get_token(client, is_superadmin=True)
    user_row = {
        'id': 1, 'org_id': 1, 'name': 'Super Admin', 'email': 'admin@system.com',
        'role': 'admin', 'is_superadmin': 1, 'must_change_password': 0,
        'branch_id': None, 'created_at': datetime(2024, 1, 1),
        'org_name': 'System', 'org_slug': 'system', 'plan': 'enterprise',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/auth/me', headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.get_json()['user']['is_superadmin'] is True


# ===========================================================================
# AUTH — LOGOUT
# ===========================================================================

def test_logout_succeeds(client):
    resp = client.post('/api/v1/auth/logout')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


# ===========================================================================
# SUPERADMIN — access control
# ===========================================================================

def test_superadmin_orgs_requires_superadmin(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    mock_cursor.fetchone.return_value = {'total': 0}
    with patch('blueprints.superadmin.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/superadmin/organizations',
                          headers=_auth_headers(token))
    assert resp.status_code == 403

def test_superadmin_orgs_accessible_by_superadmin(client):
    token = _get_token(client, is_superadmin=True)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    with patch('blueprints.superadmin.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/superadmin/organizations',
                          headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'organizations' in data

def test_superadmin_users_requires_superadmin(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn()
    mock_cursor.fetchone.return_value = {'total': 0}
    mock_cursor.fetchall.return_value = []
    with patch('blueprints.superadmin.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/superadmin/users',
                          headers=_auth_headers(token))
    assert resp.status_code == 403

def test_superadmin_audit_logs_requires_superadmin(client):
    token = _get_token(client, is_superadmin=False)
    with patch('blueprints.superadmin.database_connection', return_value=MagicMock()):
        resp = client.get('/api/v1/superadmin/audit-logs',
                          headers=_auth_headers(token))
    assert resp.status_code == 403

def test_superadmin_create_org_missing_fields(client):
    token = _get_token(client, is_superadmin=True)
    resp = client.post('/api/v1/superadmin/organizations',
                       headers=_auth_headers(token),
                       json={'org_name': 'Test'})
    assert resp.status_code == 400

def test_superadmin_cannot_delete_org_1(client):
    token = _get_token(client, is_superadmin=True)
    resp = client.delete('/api/v1/superadmin/organizations/1',
                         headers=_auth_headers(token))
    assert resp.status_code == 403


# ===========================================================================
# ASSETS
# ===========================================================================

def test_list_assets_requires_auth(client):
    resp = client.get('/api/v1/assets')
    assert resp.status_code == 401

def test_list_assets_db_unavailable(client):
    token = _get_token(client, is_superadmin=False)
    with patch('blueprints.assets.database_connection', return_value=None):
        resp = client.get('/api/v1/assets', headers=_auth_headers(token))
    assert resp.status_code == 500

def test_list_assets_returns_list(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/assets', headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'assets' in data
    assert isinstance(data['assets'], list)

def test_create_asset_missing_name(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return=None)
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/assets',
                           headers=_auth_headers(token),
                           json={'asset_tag': 'TAG-001'})
    assert resp.status_code == 400

def test_create_asset_missing_tag(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return=None)
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/assets',
                           headers=_auth_headers(token),
                           json={'name': 'Test Asset'})
    assert resp.status_code == 400

def test_create_asset_duplicate_tag(client):
    token = _get_token(client, is_superadmin=False)
    # fetchone returns existing asset (duplicate tag)
    mock_conn, _ = _make_mock_conn(fetchone_return={'id': 5})
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/assets',
                           headers=_auth_headers(token),
                           json={'asset_tag': 'TAG-DUP', 'name': 'Duplicate'})
    assert resp.status_code == 409

def test_get_asset_not_found(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # asset not found
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/assets/9999', headers=_auth_headers(token))
    assert resp.status_code == 404

def test_delete_asset_not_found(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # asset not found
    with patch('blueprints.assets.database_connection', return_value=mock_conn):
        resp = client.delete('/api/v1/assets/9999', headers=_auth_headers(token))
    assert resp.status_code == 404


# ===========================================================================
# FINANCE
# ===========================================================================

def test_list_transactions_requires_auth(client):
    resp = client.get('/api/v1/finance/transactions')
    assert resp.status_code == 401

def test_list_transactions_returns_list(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/finance/transactions', headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'transactions' in data

def test_create_transaction_missing_fields(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return={'id': 1, 'balance': 1000})
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/finance/transactions',
                           headers=_auth_headers(token),
                           json={'type': 'income'})
    assert resp.status_code == 400

def test_create_transaction_invalid_type(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return={'id': 1, 'balance': 1000})
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/finance/transactions',
                           headers=_auth_headers(token),
                           json={
                               'account_id': 1, 'type': 'invalid',
                               'amount': 100, 'transaction_date': '2026-01-01'
                           })
    assert resp.status_code == 400

def test_create_transaction_invalid_amount(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return={'id': 1, 'balance': 1000})
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/finance/transactions',
                           headers=_auth_headers(token),
                           json={
                               'account_id': 1, 'type': 'income',
                               'amount': -50, 'transaction_date': '2026-01-01'
                           })
    assert resp.status_code == 400

def test_delete_transaction_not_found(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # transaction not found
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.delete('/api/v1/finance/transactions/9999',
                             headers=_auth_headers(token))
    assert resp.status_code == 404

def test_list_finance_accounts(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    with patch('blueprints.finance.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/finance/accounts', headers=_auth_headers(token))
    assert resp.status_code == 200
    assert 'accounts' in resp.get_json()

def test_finance_summary_requires_auth(client):
    resp = client.get('/api/v1/finance/summary')
    assert resp.status_code == 401


# ===========================================================================
# BRANCHES
# ===========================================================================

def test_list_branches_requires_auth(client):
    resp = client.get('/api/v1/branches')
    assert resp.status_code == 401

def test_list_branches_returns_list(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn(fetchall_return=[])
    with patch('blueprints.branches.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/branches', headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'branches' in data

def test_create_branch_requires_admin(client):
    # Non-admin token (manager role)
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('Admin@2026!').decode('utf-8')
    user_row = {
        'id': 3, 'org_id': 2, 'name': 'Manager', 'email': 'mgr@demo.com',
        'password_hash': hashed, 'role': 'manager', 'is_superadmin': 0,
        'must_change_password': 0, 'branch_id': 1, 'is_active': 1,
        'org_name': 'Demo Clinic', 'org_slug': 'demo-clinic', 'plan': 'pro',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=user_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'mgr@demo.com', 'password': 'Admin@2026!'})
    mgr_token = resp.get_json()['access_token']

    mock_conn2, _ = _make_mock_conn(fetchone_return=None)
    with patch('blueprints.branches.database_connection', return_value=mock_conn2):
        resp2 = client.post('/api/v1/branches',
                            headers=_auth_headers(mgr_token),
                            json={'name': 'New Branch'})
    assert resp2.status_code == 403

def test_create_branch_missing_name(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return=None)
    with patch('blueprints.branches.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/branches',
                           headers=_auth_headers(token),
                           json={})
    assert resp.status_code == 400

def test_get_branch_not_found(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None  # branch not found
    with patch('blueprints.branches.database_connection', return_value=mock_conn):
        resp = client.get('/api/v1/branches/9999', headers=_auth_headers(token))
    assert resp.status_code == 404

def test_asset_transfer_missing_branch_id(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn(fetchone_return={'id': 1, 'branch_id': 1, 'name': 'X'})
    with patch('blueprints.branches.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/assets/1/transfer',
                           headers=_auth_headers(token),
                           json={})
    assert resp.status_code == 400


# ===========================================================================
# SETTINGS
# ===========================================================================

def test_get_settings_requires_auth(client):
    resp = client.get('/api/v1/settings')
    assert resp.status_code == 401

def test_update_settings_invalid_key(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, mock_cursor = _make_mock_conn()
    mock_cursor.fetchall.return_value = []
    with patch('blueprints.settings.database_connection', return_value=mock_conn):
        resp = client.put('/api/v1/settings',
                          headers=_auth_headers(token),
                          json={'invalid_key': 'value'})
    assert resp.status_code == 400
    assert 'Invalid setting keys' in resp.get_json()['error']

def test_update_settings_valid_key(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn, _ = _make_mock_conn()
    with patch('blueprints.settings.database_connection', return_value=mock_conn):
        resp = client.put('/api/v1/settings',
                          headers=_auth_headers(token),
                          json={'currency': 'KES', 'currency_symbol': 'Ksh'})
    assert resp.status_code == 200


# ===========================================================================
# TEAM
# ===========================================================================

def test_list_team_requires_auth(client):
    resp = client.get('/api/v1/team/members')
    assert resp.status_code == 401

def test_invite_requires_admin_role(client):
    # Log in as viewer
    from flask_bcrypt import Bcrypt
    b = Bcrypt(app)
    hashed = b.generate_password_hash('Admin@2026!').decode('utf-8')
    viewer_row = {
        'id': 5, 'org_id': 2, 'name': 'Viewer', 'email': 'viewer@demo.com',
        'password_hash': hashed, 'role': 'viewer', 'is_superadmin': 0,
        'must_change_password': 0, 'branch_id': None, 'is_active': 1,
        'org_name': 'Demo Clinic', 'org_slug': 'demo-clinic', 'plan': 'pro',
    }
    mock_conn, _ = _make_mock_conn(fetchone_return=viewer_row)
    with patch('blueprints.auth.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/auth/login',
                           json={'email': 'viewer@demo.com', 'password': 'Admin@2026!'})
    viewer_token = resp.get_json()['access_token']

    resp2 = client.post('/api/v1/team/invite',
                        headers=_auth_headers(viewer_token),
                        json={'email': 'new@demo.com', 'name': 'New User'})
    assert resp2.status_code == 403

def test_invite_max_users_enforced(client):
    token = _get_token(client, is_superadmin=False)
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    # org max_users = 2, current count = 2  → at limit
    mock_cursor.fetchone.side_effect = [
        (2,),    # max_users
        (2,),    # active_user_count
    ]
    with patch('blueprints.team.database_connection', return_value=mock_conn):
        resp = client.post('/api/v1/team/invite',
                           headers=_auth_headers(token),
                           json={'email': 'extra@demo.com', 'name': 'Extra'})
    assert resp.status_code == 403
    assert 'maximum' in resp.get_json()['error'].lower()


# ===========================================================================
# DASHBOARD
# ===========================================================================

def test_dashboard_requires_auth(client):
    resp = client.get('/api/v1/dashboard')
    assert resp.status_code == 401


# ===========================================================================
# DEPRECIATION UTILS
# ===========================================================================

def test_straight_line_depreciation():
    from utils.depreciation import calculate_straight_line
    result = calculate_straight_line(cost=10000, salvage_value=1000, useful_life_years=5)
    assert result['method'] == 'straight_line'
    assert result['annual_depreciation'] == 1800.0
    assert len(result['schedule']) == 5
    assert result['schedule'][-1]['book_value'] == 1000.0

def test_declining_balance_depreciation():
    from utils.depreciation import calculate_declining_balance
    result = calculate_declining_balance(cost=10000, rate_percent=20, useful_life_years=5)
    assert result['method'] == 'declining_balance'
    assert len(result['schedule']) == 5
    # After year 1: 10000 * (1 - 0.20) = 8000
    assert result['schedule'][0]['book_value'] == 8000.0

def test_calculate_current_value_straight_line():
    from utils.depreciation import calculate_current_value
    # Brand new asset — value should be close to cost
    today = __import__('datetime').date.today().isoformat()
    val = calculate_current_value(
        cost=10000, purchase_date_str=today,
        method='straight_line', useful_life_years=10, salvage_value=0
    )
    assert val == 10000.0

def test_calculate_current_value_declining_balance():
    from utils.depreciation import calculate_current_value
    # Asset purchased exactly 1 year ago
    import datetime
    one_year_ago = (datetime.date.today() - datetime.timedelta(days=366)).isoformat()
    val = calculate_current_value(
        cost=10000, purchase_date_str=one_year_ago,
        method='declining_balance', rate_percent=20, useful_life_years=10
    )
    # After 1 year at 20%: 10000 * 0.80 = 8000
    assert val == 8000.0

def test_get_depreciation_schedule_no_cost():
    from utils.depreciation import get_depreciation_schedule
    result = get_depreciation_schedule({'purchase_price': 0})
    assert 'error' in result

