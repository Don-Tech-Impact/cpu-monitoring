from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt
from app import database_connection, require_org

settings_bp = Blueprint('settings', __name__)

# Allowlist of permitted setting keys
ALLOWED_SETTING_KEYS = {
    'currency',
    'currency_symbol',
    'date_format',
    'fiscal_year_start',
    'tax_rate',
    'business_address',
    'business_phone',
    'business_email',
    'tax_id',
    'company_name',
    'timezone'
}


@settings_bp.route('/settings', methods=['GET'])
@require_org
def get_settings():
    """Get all settings for the organization"""
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
            "SELECT setting_key, setting_value FROM organization_settings WHERE org_id = %s",
            (org_id,)
        )
        settings = cursor.fetchall()
        
        # Convert to dictionary
        settings_dict = {}
        for setting in settings:
            settings_dict[setting['setting_key']] = setting['setting_value']
        
        return jsonify({'success': True, 'data': settings_dict}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@settings_bp.route('/settings', methods=['PUT'])
@require_org
def update_settings():
    """Update organization settings"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    # Only admins can update settings
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can update settings'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Validate that all keys are in allowlist
    invalid_keys = set(data.keys()) - ALLOWED_SETTING_KEYS
    if invalid_keys:
        return jsonify({
            'success': False,
            'error': f'Invalid setting keys: {", ".join(sorted(invalid_keys))}. Allowed keys: {", ".join(sorted(ALLOWED_SETTING_KEYS))}'
        }), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Update each setting
        for key, value in data.items():
            cursor.execute(
                """INSERT INTO organization_settings (org_id, setting_key, setting_value) 
                   VALUES (%s, %s, %s) 
                   ON DUPLICATE KEY UPDATE setting_value = %s""",
                (org_id, key, str(value), str(value))
            )
        
        conn.commit()
        return jsonify({'success': True, 'message': 'Settings updated successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@settings_bp.route('/settings/logo', methods=['GET'])
@require_org
def get_logo():
    """Get organization logo"""
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
            "SELECT logo_path FROM organizations WHERE id = %s",
            (org_id,)
        )
        org = cursor.fetchone()
        
        if not org:
            return jsonify({'success': False, 'error': 'Organization not found'}), 404
            
        return jsonify({'success': True, 'data': {'logo_url': org.get('logo_path', '')}}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@settings_bp.route('/settings/logo', methods=['POST'])
@require_org
def upload_logo():
    """Upload organization logo"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    # Only admins can upload logo
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can upload logo'}), 403
    
    # In a real implementation, this would handle file upload
    # For now, we'll accept a URL
    data = request.get_json()
    if not data or 'logo_url' not in data:
        return jsonify({'success': False, 'error': 'Logo URL required'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE organizations SET logo_path = %s WHERE id = %s",
            (data['logo_url'], org_id)
        )
        conn.commit()
        return jsonify({'success': True, 'message': 'Logo updated successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
