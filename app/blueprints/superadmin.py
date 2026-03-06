"""
Superadmin blueprint
Routes (all prefixed with /api/v1/superadmin in app.py):
  GET    /dashboard                                  — superadmin dashboard with stats
  GET    /system-settings                            — get system-wide settings
  PUT    /system-settings                            — update system settings
  POST   /organizations                              — create new organization with admin
  GET    /organizations                              — list all organizations
  GET    /organizations/<id>                         — get organization details
  PUT    /organizations/<id>                         — update organization
  DELETE /organizations/<id>                         — delete organization (prevent id=1)
  POST   /organizations/<id>/suspend                 — suspend organization
  POST   /organizations/<id>/reactivate              — reactivate organization
  GET    /users                                      — list all users across orgs
  PUT    /users/<id>/toggle-status                   — activate/deactivate user
  PUT    /users/<id>/reset-password                  — reset user password
  GET    /audit-logs                                 — get paginated audit logs
  GET    /activity-stats                             — real-time activity statistics
"""

import re
import secrets
import string
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required
from app import bcrypt, database_connection

superadmin_bp = Blueprint('superadmin', __name__)


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


def _generate_temp_password(length: int = 12) -> str:
    """
    Generate a cryptographically secure temporary password.
    Must include uppercase, lowercase, digits, and symbols.
    """
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*"
    
    # Ensure at least one of each character type
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    
    # Fill the rest with random choices from all character types
    all_chars = uppercase + lowercase + digits + symbols
    password += [secrets.choice(all_chars) for _ in range(length - 4)]
    
    # Shuffle to avoid predictable pattern
    shuffled = list(password)
    secrets.SystemRandom().shuffle(shuffled)
    return ''.join(shuffled)


def _check_superadmin(claims: dict) -> tuple[bool, dict | None]:
    """
    Check if user has superadmin claim.
    Returns (is_superadmin, error_response)
    """
    is_superadmin = claims.get('is_superadmin', False)
    if not is_superadmin:
        error_response = jsonify({
            'success': False,
            'error': 'Permission denied. Superadmin access required'
        })
        return False, error_response
    return True, None


def _write_audit_log(conn, org_id: int, action: str, details: str, user_id: int = None):
    """Write an audit log entry."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO audit_logs (org_id, user_id, action, details, ip_address)
               VALUES (%s, %s, %s, %s, %s)""",
            (org_id, user_id, action, details, request.remote_addr)
        )
        cursor.close()
    except Exception as e:
        # Don't fail the main operation if audit log fails
        pass


# ---------------------------------------------------------------------------
# GET /dashboard — Superadmin Dashboard Statistics
# ---------------------------------------------------------------------------
@superadmin_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """Get comprehensive dashboard statistics for superadmin"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Total organizations (excluding system org)
        cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE id > 1")
        total_orgs = cursor.fetchone()['count']
        
        # Active organizations
        cursor.execute("SELECT COUNT(*) as count FROM organizations WHERE id > 1 AND is_active = TRUE")
        active_orgs = cursor.fetchone()['count']
        
        # Total users
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_users = cursor.fetchone()['count']
        
        # Active users
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = TRUE")
        active_users = cursor.fetchone()['count']
        
        # Total assets
        cursor.execute("SELECT COUNT(*) as count FROM assets")
        total_assets = cursor.fetchone()['count']
        
        # Total transactions
        cursor.execute("SELECT COUNT(*) as count FROM transactions")
        total_transactions = cursor.fetchone()['count']
        
        # Recent organizations (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) as count FROM organizations 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND id > 1
        """)
        recent_orgs = cursor.fetchone()['count']
        
        # Recent users (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        recent_users = cursor.fetchone()['count']
        
        # Organizations by plan
        cursor.execute("""
            SELECT plan, COUNT(*) as count 
            FROM organizations 
            WHERE id > 1 
            GROUP BY plan
        """)
        orgs_by_plan = {row['plan']: row['count'] for row in cursor.fetchall()}
        
        # Top 5 organizations by user count
        cursor.execute("""
            SELECT o.id, o.name, COUNT(u.id) as user_count
            FROM organizations o
            LEFT JOIN users u ON o.id = u.org_id
            WHERE o.id > 1
            GROUP BY o.id, o.name
            ORDER BY user_count DESC
            LIMIT 5
        """)
        top_orgs = cursor.fetchall()
        
        # Recent audit activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) as count FROM audit_logs 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        recent_activity = cursor.fetchone()['count']
        
        # System health metrics
        cursor.execute("SELECT COUNT(*) as count FROM assets WHERE status = 'active'")
        active_assets = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT SUM(balance) as total FROM accounts WHERE org_id > 1
        """)
        total_balance_result = cursor.fetchone()
        total_balance = float(total_balance_result['total']) if total_balance_result['total'] else 0.0
        
        return jsonify({
            'success': True,
            'stats': {
                'organizations': {
                    'total': total_orgs,
                    'active': active_orgs,
                    'suspended': total_orgs - active_orgs,
                    'recent_7_days': recent_orgs,
                    'by_plan': orgs_by_plan
                },
                'users': {
                    'total': total_users,
                    'active': active_users,
                    'inactive': total_users - active_users,
                    'recent_7_days': recent_users
                },
                'assets': {
                    'total': total_assets,
                    'active': active_assets
                },
                'financial': {
                    'total_transactions': total_transactions,
                    'total_balance': total_balance
                },
                'activity': {
                    'last_24_hours': recent_activity
                },
                'top_organizations': top_orgs
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /system-settings — Get system-wide settings
# ---------------------------------------------------------------------------
@superadmin_bp.route('/system-settings', methods=['GET'])
@jwt_required()
def get_system_settings():
    """Get system-wide configuration settings"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get settings from organization_settings for org_id = 1 (system settings)
        cursor.execute("""
            SELECT setting_key, setting_value 
            FROM organization_settings 
            WHERE org_id = 1
        """)
        settings_rows = cursor.fetchall()
        settings = {row['setting_key']: row['setting_value'] for row in settings_rows}
        
        # Default settings if none exist
        if not settings:
            settings = {
                'maintenance_mode': 'false',
                'allow_new_registrations': 'true',
                'max_file_upload_mb': '10',
                'session_timeout_minutes': '30',
                'password_expiry_days': '90',
                'enable_audit_logs': 'true',
                'default_currency': 'USD',
                'default_plan': 'basic'
            }
        
        return jsonify({
            'success': True,
            'settings': settings
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /system-settings — Update system settings
# ---------------------------------------------------------------------------
@superadmin_bp.route('/system-settings', methods=['PUT'])
@jwt_required()
def update_system_settings():
    """Update system-wide configuration settings"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Update or insert each setting
        for key, value in data.items():
            cursor.execute("""
                INSERT INTO organization_settings (org_id, setting_key, setting_value)
                VALUES (1, %s, %s)
                ON DUPLICATE KEY UPDATE setting_value = %s
            """, (key, str(value), str(value)))
        
        conn.commit()
        
        # Log the action
        user_id = claims.get('sub')
        _write_audit_log(conn, 1, 'SYSTEM_SETTINGS_UPDATE', 
                        f'Updated system settings: {", ".join(data.keys())}', user_id)
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'System settings updated successfully'
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /activity-stats — Real-time activity statistics
# ---------------------------------------------------------------------------
@superadmin_bp.route('/activity-stats', methods=['GET'])
@jwt_required()
def get_activity_stats():
    """Get real-time activity statistics"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Activity in last hour
        cursor.execute("""
            SELECT action, COUNT(*) as count 
            FROM audit_logs 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            GROUP BY action
            ORDER BY count DESC
            LIMIT 10
        """)
        recent_actions = cursor.fetchall()
        
        # Most active organizations (last 24 hours)
        cursor.execute("""
            SELECT o.name, COUNT(al.id) as activity_count
            FROM audit_logs al
            JOIN organizations o ON al.org_id = o.id
            WHERE al.created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY o.id, o.name
            ORDER BY activity_count DESC
            LIMIT 5
        """)
        active_orgs = cursor.fetchall()
        
        # Most active users (last 24 hours)
        cursor.execute("""
            SELECT u.name, u.email, COUNT(al.id) as activity_count
            FROM audit_logs al
            JOIN users u ON al.user_id = u.id
            WHERE al.created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY u.id, u.name, u.email
            ORDER BY activity_count DESC
            LIMIT 5
        """)
        active_users = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'activity': {
                'recent_actions': recent_actions,
                'most_active_organizations': active_orgs,
                'most_active_users': active_users
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /organizations — Create organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations', methods=['POST'])
@jwt_required()
def create_organization():
    """Create a new organization with admin user (superadmin only)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Validate required fields
    required_fields = ['org_name', 'admin_email', 'admin_name']
    missing = [f for f in required_fields if f not in data or not data[f]]
    if missing:
        return jsonify({
            'success': False,
            'error': f'Missing required fields: {", ".join(missing)}'
        }), 400
    
    # Extract and validate inputs
    org_name = data['org_name'].strip()
    admin_email = data['admin_email'].strip().lower()
    admin_name = data['admin_name'].strip()
    plan = data.get('plan', 'free').strip()
    max_users = data.get('max_users', 5)
    max_assets = data.get('max_assets', 100)
    
    # Validate email format
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', admin_email):
        return jsonify({'success': False, 'error': 'Invalid email format'}), 400
    
    # Validate plan
    valid_plans = ['free', 'starter', 'professional', 'enterprise']
    if plan not in valid_plans:
        plan = 'free'
    
    # Validate numeric limits
    try:
        max_users = int(max_users)
        max_assets = int(max_assets)
        if max_users < 1:
            max_users = 5
        if max_assets < 1:
            max_assets = 100
    except (ValueError, TypeError):
        max_users = 5
        max_assets = 100
    
    # Generate secure temp password
    temp_password = _generate_temp_password(12)
    password_hash = bcrypt.generate_password_hash(temp_password).decode('utf-8')
    
    # Slugify org name
    slug = _slugify(org_name)
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check if email is already registered
        cursor.execute("SELECT id FROM users WHERE email = %s", (admin_email,))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Email already registered'}), 409
        
        # Check slug uniqueness and append random suffix if collision
        cursor.execute("SELECT id FROM organizations WHERE slug = %s", (slug,))
        if cursor.fetchone():
            suffix = secrets.token_hex(3)
            slug = f"{slug}-{suffix}"
        
        # Create organization with max_users and max_assets
        cursor.execute(
            """INSERT INTO organizations (name, slug, plan, is_active, max_users, max_assets)
               VALUES (%s, %s, %s, TRUE, %s, %s)""",
            (org_name, slug, plan, max_users, max_assets)
        )
        org_id = cursor.lastrowid
        
        # Create admin user with must_change_password=TRUE
        cursor.execute(
            """INSERT INTO users (org_id, name, email, password_hash, role, must_change_password, is_active)
               VALUES (%s, %s, %s, %s, 'admin', TRUE, TRUE)""",
            (org_id, admin_name, admin_email, password_hash)
        )
        user_id = cursor.lastrowid
        
        # Write audit log
        _write_audit_log(
            conn,
            org_id,
            'org_created',
            f'Organization created: {org_name}, Admin email: {admin_email}',
            claims.get('user_id')
        )
        
        conn.commit()

        return jsonify({
            'success': True,
            'message': 'Organization created successfully',
            'data': {
                'org_id': org_id,
                'org_name': org_name,
                'slug': slug,
                'admin_email': admin_email,
                'temp_password': temp_password,
                'plan': plan,
                'max_users': max_users,
                'max_assets': max_assets,
            }
        }), 201
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /superadmin/organizations — List all organizations
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations', methods=['GET'])
@jwt_required()
def list_organizations():
    """List all organizations (exclude id=1) with user counts"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT o.id, o.name, o.slug, o.plan, o.is_active, o.max_users, o.max_assets,
                      o.created_at,
                      (SELECT COUNT(*) FROM users WHERE org_id = o.id) as user_count
               FROM organizations o
               WHERE o.id != 1
               ORDER BY o.created_at DESC"""
        )
        organizations = cursor.fetchall()
        
        # Convert datetime objects to ISO format strings
        for org in organizations:
            if org.get('created_at'):
                org['created_at'] = org['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'organizations': organizations,
            'count': len(organizations)
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /superadmin/organizations/<int:org_id> — Get single organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations/<int:org_id>', methods=['GET'])
@jwt_required()
def get_organization(org_id):
    """Get organization details with user list"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get organization
        cursor.execute(
            """SELECT o.id, o.name, o.slug, o.plan, o.is_active, o.max_users, o.max_assets,
                      o.created_at,
                      (SELECT COUNT(*) FROM users WHERE org_id = o.id) as user_count
               FROM organizations o
               WHERE o.id = %s""",
            (org_id,)
        )
        org = cursor.fetchone()
        
        if not org:
            return jsonify({'success': False, 'error': 'Organization not found'}), 404
        
        # Get users in organization
        cursor.execute(
            """SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at
               FROM users u
               WHERE u.org_id = %s
               ORDER BY u.created_at DESC""",
            (org_id,)
        )
        users = cursor.fetchall()
        
        # Convert datetime objects
        if org.get('created_at'):
            org['created_at'] = org['created_at'].isoformat()
        for user in users:
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
        
        org['users'] = users
        
        return jsonify({
            'success': True,
            'data': org
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /superadmin/organizations/<int:org_id> — Update organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations/<int:org_id>', methods=['PUT'])
@jwt_required()
def update_organization(org_id):
    """Update organization (name, plan, is_active, max_users, max_assets)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check if organization exists
        cursor.execute("SELECT id FROM organizations WHERE id = %s", (org_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Organization not found'}), 404
        
        # Build dynamic update query
        update_fields = []
        values = []
        allowed_fields = ['name', 'plan', 'is_active', 'max_users', 'max_assets']
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                values.append(data[field])
        
        if not update_fields:
            return jsonify({
                'success': False,
                'error': f'No valid fields to update. Allowed: {", ".join(allowed_fields)}'
            }), 400
        
        values.append(org_id)
        
        cursor.execute(
            f"UPDATE organizations SET {', '.join(update_fields)} WHERE id = %s",
            values
        )
        
        # Write audit log
        _write_audit_log(
            conn,
            org_id,
            'org_updated',
            f'Organization updated with fields: {", ".join(update_fields)}',
            claims.get('user_id')
        )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Organization updated successfully'
        }), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /superadmin/organizations/<int:org_id>/suspend — Suspend organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations/<int:org_id>/suspend', methods=['POST'])
@jwt_required()
def suspend_organization(org_id):
    """Suspend organization (set is_active=False, deactivate all users)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor()
        
        # Check if organization exists
        cursor.execute("SELECT id FROM organizations WHERE id = %s", (org_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Organization not found'}), 404

        # Set organization as inactive
        cursor.execute(
            "UPDATE organizations SET is_active = FALSE WHERE id = %s",
            (org_id,)
        )
        
        # Deactivate all users in organization
        cursor.execute(
            "UPDATE users SET is_active = FALSE WHERE org_id = %s",
            (org_id,)
        )
        
        # Write audit log
        _write_audit_log(
            conn,
            org_id,
            'org_suspended',
            'Organization suspended and all users deactivated',
            claims.get('user_id')
        )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Organization suspended successfully'
        }), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# POST /superadmin/organizations/<int:org_id>/reactivate — Reactivate organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations/<int:org_id>/reactivate', methods=['POST'])
@jwt_required()
def reactivate_organization(org_id):
    """Reactivate organization (set is_active=True)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor()
        
        # Check if organization exists
        cursor.execute("SELECT id FROM organizations WHERE id = %s", (org_id,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Organization not found'}), 404

        # Set organization as active
        cursor.execute(
            "UPDATE organizations SET is_active = TRUE WHERE id = %s",
            (org_id,)
        )
        
        # Write audit log
        _write_audit_log(
            conn,
            org_id,
            'org_reactivated',
            'Organization reactivated',
            claims.get('user_id')
        )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Organization reactivated successfully'
        }), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# DELETE /superadmin/organizations/<int:org_id> — Delete organization
# ---------------------------------------------------------------------------
@superadmin_bp.route('/organizations/<int:org_id>', methods=['DELETE'])
@jwt_required()
def delete_organization(org_id):
    """Delete organization (prevent deletion of org id=1)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    # Prevent deletion of system admin organization
    if org_id == 1:
        return jsonify({
            'success': False,
            'error': 'Cannot delete system admin organization (id=1)'
        }), 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor()
        
        # Check if organization exists
        cursor.execute("SELECT id, name FROM organizations WHERE id = %s", (org_id,))
        org = cursor.fetchone()
        if not org:
            return jsonify({'success': False, 'error': 'Organization not found'}), 404
        
        # Delete organization (cascade will handle related data)
        cursor.execute("DELETE FROM organizations WHERE id = %s", (org_id,))
        
        # Write audit log before organization is deleted
        try:
            cursor.execute(
                """INSERT INTO audit_logs (org_id, user_id, action, details, ip_address)
                   VALUES (%s, %s, %s, %s, %s)""",
                (org_id, claims.get('user_id'), 'org_deleted', f'Organization deleted: {org[1]}', request.remote_addr)
            )
        except Exception:
            pass
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Organization deleted successfully'
        }), 200
    
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /superadmin/users — List all users across all organizations
# ---------------------------------------------------------------------------
@superadmin_bp.route('/users', methods=['GET'])
@jwt_required()
def list_all_users():
    """List all users across all organizations (superadmin only)"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    org_id_filter = request.args.get('org_id', type=int)
    
    if limit > 500:
        limit = 500
    if limit < 1:
        limit = 50
    if page < 1:
        page = 1
    
    offset = (page - 1) * limit
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Build query based on filters
        where_clause = "WHERE u.is_superadmin = 0"
        params = []
        
        if org_id_filter:
            where_clause += " AND u.org_id = %s"
            params.append(org_id_filter)
        
        # Get total count
        cursor.execute(
            f"SELECT COUNT(*) as total FROM users u {where_clause}",
            params
        )
        total = cursor.fetchone()['total']
        
        # Get paginated users
        cursor.execute(
            f"""SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at,
                      o.id as org_id, o.name as org_name, o.slug as org_slug
               FROM users u
               LEFT JOIN organizations o ON u.org_id = o.id
               {where_clause}
               ORDER BY u.created_at DESC
               LIMIT %s OFFSET %s""",
            params + [limit, offset]
        )
        users = cursor.fetchall()
        
        # Convert datetime objects
        for user in users:
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'users': users,
            'count': len(users),
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /users/<id>/toggle-status — Toggle user active status
# ---------------------------------------------------------------------------
@superadmin_bp.route('/users/<int:user_id>/toggle-status', methods=['PUT'])
@jwt_required()
def toggle_user_status(user_id):
    """Activate or deactivate a user (superadmin only)"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if user exists
        cursor.execute("SELECT id, email, is_active, org_id FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Toggle status
        new_status = not user['is_active']
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        
        # Log the action
        admin_id = claims.get('sub')
        action = 'USER_ACTIVATED' if new_status else 'USER_DEACTIVATED'
        _write_audit_log(conn, user['org_id'], action, 
                        f"User {user['email']} {'activated' if new_status else 'deactivated'} by superadmin", 
                        admin_id)
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f"User {'activated' if new_status else 'deactivated'} successfully",
            'user': {
                'id': user_id,
                'email': user['email'],
                'is_active': new_status
            }
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# PUT /users/<id>/reset-password — Reset user password
# ---------------------------------------------------------------------------
@superadmin_bp.route('/users/<int:user_id>/reset-password', methods=['PUT'])
@jwt_required()
def reset_user_password(user_id):
    """Reset a user's password and force them to change it (superadmin only)"""
    claims = get_jwt()
    is_super, error_resp = _check_superadmin(claims)
    if not is_super:
        return error_resp, 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if user exists
        cursor.execute("SELECT id, email, name, org_id FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Generate temporary password
        temp_password = _generate_temp_password()
        password_hash = bcrypt.generate_password_hash(temp_password, rounds=12).decode('utf-8')
        
        # Update password and force change
        cursor.execute("""
            UPDATE users 
            SET password_hash = %s, must_change_password = TRUE 
            WHERE id = %s
        """, (password_hash, user_id))
        conn.commit()
        
        # Log the action
        admin_id = claims.get('sub')
        _write_audit_log(conn, user['org_id'], 'PASSWORD_RESET', 
                        f"Password reset for user {user['email']} by superadmin", 
                        admin_id)
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Password reset successfully. User must change password on next login.',
            'temp_password': temp_password,
            'user': {
                'id': user_id,
                'email': user['email'],
                'name': user['name']
            }
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# GET /superadmin/audit-logs — Get paginated, filterable audit logs
# ---------------------------------------------------------------------------
@superadmin_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """Get audit logs (superadmin only) with pagination and filtering"""
    claims = get_jwt()
    is_admin, error_resp = _check_superadmin(claims)
    if not is_admin:
        return error_resp, 403
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 100, type=int)
    org_id_filter = request.args.get('org_id', type=int)
    action_filter = request.args.get('action', type=str)
    from_date = request.args.get('from_date', type=str)
    to_date = request.args.get('to_date', type=str)
    
    if limit > 500:
        limit = 500
    if limit < 1:
        limit = 100
    if page < 1:
        page = 1
    
    offset = (page - 1) * limit
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Build dynamic where clause
        where_clauses = []
        params = []
        
        if org_id_filter:
            where_clauses.append("al.org_id = %s")
            params.append(org_id_filter)
        
        if action_filter:
            where_clauses.append("al.action = %s")
            params.append(action_filter)
        
        if from_date:
            where_clauses.append("al.created_at >= %s")
            params.append(from_date)
        
        if to_date:
            where_clauses.append("al.created_at <= %s")
            params.append(to_date)
        
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Get total count
        cursor.execute(
            f"""SELECT COUNT(*) as total FROM audit_logs al {where_clause}""",
            params
        )
        total = cursor.fetchone()['total']
        
        # Get paginated logs
        cursor.execute(
            f"""SELECT al.id, al.org_id, al.user_id, al.action, al.details, al.ip_address,
                      al.created_at, u.email as user_email, o.name as org_name
               FROM audit_logs al
               LEFT JOIN users u ON al.user_id = u.id
               LEFT JOIN organizations o ON al.org_id = o.id
               {where_clause}
               ORDER BY al.created_at DESC
               LIMIT %s OFFSET %s""",
            params + [limit, offset]
        )
        logs = cursor.fetchall()
        
        # Convert datetime objects
        for log in logs:
            if log.get('created_at'):
                log['created_at'] = log['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'audit_logs': logs,
            'count': len(logs),
            'total': total,
            'page': page,
            'limit': limit,
            'pages': (total + limit - 1) // limit
        }), 200
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
