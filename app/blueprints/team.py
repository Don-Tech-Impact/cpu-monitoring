from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt
from app import database_connection, require_org, bcrypt
import secrets
import re
from datetime import datetime, timedelta

team_bp = Blueprint('team', __name__)


def generate_invite_token():
    """Generate a secure invitation token"""
    return secrets.token_urlsafe(32)


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


@team_bp.route('/team/members', methods=['GET'])
@require_org
def list_team_members():
    """List all team members for the organization"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """SELECT id, name, email, role, is_active, created_at 
               FROM users WHERE org_id = %s ORDER BY created_at DESC""",
            (org_id,)
        )
        members = cursor.fetchall()
        
        return jsonify({'success': True, 'data': members}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@team_bp.route('/team/invite', methods=['POST'])
@require_org
def invite_member():
    """Invite a new team member"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    user_id = claims.get('user_id')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    # Only admins can invite members
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can invite team members'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required_fields = ['email', 'name']
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({'success': False, 'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Check max_users limit on organization
        cursor.execute(
            "SELECT max_users FROM organizations WHERE id = %s",
            (org_id,)
        )
        org_row = cursor.fetchone()
        if not org_row:
            return jsonify({'success': False, 'error': 'Organization not found'}), 404
        
        max_users = org_row[0]
        
        # Count active users in organization
        cursor.execute(
            "SELECT COUNT(*) FROM users WHERE org_id = %s AND is_active = TRUE",
            (org_id,)
        )
        active_user_count = cursor.fetchone()[0]
        
        # Check if at limit
        if max_users is not None and active_user_count >= max_users:
            return jsonify({
                'success': False,
                'error': f'Organization has reached the maximum number of users ({max_users})'
            }), 403
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (data['email'],))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'User with this email already exists'}), 409
        
        # Check for pending invitation
        cursor.execute(
            "SELECT id FROM user_invitations WHERE email = %s AND org_id = %s AND status = 'pending'",
            (data['email'], org_id)
        )
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'Invitation already sent to this email'}), 409
        
        # Generate invitation token
        token = generate_invite_token()
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        # Create invitation
        cursor.execute(
            """INSERT INTO user_invitations (org_id, email, role, invited_by, token, expires_at) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (org_id, data['email'], data.get('role', 'viewer'), user_id, token, expires_at)
        )
        
        conn.commit()
        
        # In production, send email with invitation link
        invitation_link = f"/invite/{token}"
        
        return jsonify({
            'success': True,
            'message': 'Invitation sent successfully',
            'invitation_link': invitation_link,
            'expires_at': expires_at.isoformat()
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@team_bp.route('/team/accept-invite', methods=['POST'])
def accept_invitation():
    """Accept an invitation and create user account (no auth required - public endpoint)"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required_fields = ['token', 'password', 'name']
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({'success': False, 'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Validate password strength
    password_error = _validate_password_strength(data['password'])
    if password_error:
        return jsonify({'success': False, 'error': password_error}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Check if invitation is valid (without requiring org_id from JWT)
        cursor.execute(
            """SELECT id, org_id, email, role, expires_at FROM user_invitations 
               WHERE token = %s AND status = 'pending'""",
            (data['token'],)
        )
        invitation = cursor.fetchone()
        
        if not invitation:
            return jsonify({'success': False, 'error': 'Invalid or expired invitation'}), 400
        
        # Check expiration - use the datetime object directly
        if invitation['expires_at'] < datetime.utcnow():
            return jsonify({'success': False, 'error': 'Invitation has expired'}), 400
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (invitation['email'],))
        if cursor.fetchone():
            return jsonify({'success': False, 'error': 'User with this email already exists'}), 409
        
        # Hash password with bcrypt
        hashed_password = bcrypt.generate_password_hash(data['password'], rounds=12).decode('utf-8')
        
        # Create user account with provided name
        cursor.execute(
            """INSERT INTO users (org_id, email, name, role, password_hash, is_active) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (invitation['org_id'], invitation['email'], data['name'].strip(), invitation['role'], hashed_password, True)
        )
        
        # Mark invitation as accepted
        cursor.execute(
            "UPDATE user_invitations SET status = 'accepted' WHERE id = %s",
            (invitation['id'],)
        )
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Invitation accepted. Account created successfully. You can now log in.'
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@team_bp.route('/team/members/<int:member_id>', methods=['PUT'])
@require_org
def update_team_member(member_id):
    """Update team member role"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    # Only admins can update members
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can update team members'}), 403
    
    data = request.get_json()
    if not data or 'role' not in data:
        return jsonify({'success': False, 'error': 'Role is required'}), 400
    
    if data['role'] not in ['admin', 'manager', 'accountant', 'viewer']:
        return jsonify({'success': False, 'error': 'Invalid role'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Check if member exists in organization
        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND org_id = %s",
            (member_id, org_id)
        )
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Team member not found'}), 404
        
        cursor.execute(
            "UPDATE users SET role = %s WHERE id = %s AND org_id = %s",
            (data['role'], member_id, org_id)
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Team member updated successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@team_bp.route('/team/members/<int:member_id>', methods=['DELETE'])
@require_org
def remove_team_member(member_id):
    """Remove a team member"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    user_id = claims.get('user_id')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    # Only admins can remove members
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can remove team members'}), 403
    
    # Cannot remove yourself
    if member_id == user_id:
        return jsonify({'success': False, 'error': 'Cannot remove yourself'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Check if member exists
        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND org_id = %s",
            (member_id, org_id)
        )
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Team member not found'}), 404
        
        # Deactivate instead of deleting (keep data integrity)
        cursor.execute(
            "UPDATE users SET is_active = FALSE WHERE id = %s AND org_id = %s",
            (member_id, org_id)
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Team member removed successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
