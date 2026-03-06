from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt
from app import database_connection, require_org

bank_accounts_bp = Blueprint('bank_accounts', __name__)


@bank_accounts_bp.route('/bank-accounts', methods=['GET'])
@require_org
def list_bank_accounts():
    """List all bank accounts for the organization"""
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
            """SELECT id, account_name, bank_name, account_number, account_type, is_active, created_at 
               FROM bank_accounts WHERE org_id = %s ORDER BY created_at DESC""",
            (org_id,)
        )
        accounts = cursor.fetchall()
        
        # Mask account numbers for security
        for account in accounts:
            if account.get('account_number'):
                account['account_number'] = '****' + account['account_number'][-4:] if len(account['account_number']) > 4 else '****'
        
        return jsonify({'success': True, 'data': accounts}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bank_accounts_bp.route('/bank-accounts', methods=['POST'])
@require_org
def create_bank_account():
    """Create a new bank account"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    if role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required_fields = ['account_name']
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({'success': False, 'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Validate account_type if provided
    account_type = data.get('account_type', 'checking')
    if account_type not in ['checking', 'savings', 'business']:
        return jsonify({'success': False, 'error': 'account_type must be checking, savings, or business'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO bank_accounts (org_id, account_name, bank_name, account_number, routing_number, account_type) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                org_id,
                data['account_name'],
                data.get('bank_name', ''),
                data.get('account_number', ''),
                data.get('routing_number', ''),
                account_type
            )
        )
        account_id = cursor.lastrowid
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Bank account created successfully',
            'id': account_id
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bank_accounts_bp.route('/bank-accounts/<int:account_id>', methods=['GET'])
@require_org
def get_bank_account(account_id):
    """Get a specific bank account"""
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
            """SELECT id, account_name, bank_name, account_number, routing_number, account_type, is_active, created_at 
               FROM bank_accounts WHERE id = %s AND org_id = %s""",
            (account_id, org_id)
        )
        account = cursor.fetchone()
        
        if not account:
            return jsonify({'success': False, 'error': 'Bank account not found'}), 404
        
        # Mask sensitive data
        if account.get('account_number'):
            account['account_number'] = '****' + account['account_number'][-4:] if len(account['account_number']) > 4 else '****'
        
        return jsonify({'success': True, 'data': account}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bank_accounts_bp.route('/bank-accounts/<int:account_id>', methods=['PUT'])
@require_org
def update_bank_account(account_id):
    """Update a bank account"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    if role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    # Validate account_type if provided
    if 'account_type' in data and data['account_type'] not in ['checking', 'savings', 'business']:
        return jsonify({'success': False, 'error': 'account_type must be checking, savings, or business'}), 400
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Check if account exists
        cursor.execute("SELECT id FROM bank_accounts WHERE id = %s AND org_id = %s", (account_id, org_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Bank account not found'}), 404
        
        # Build update query
        update_fields = []
        values = []
        for field in ['account_name', 'bank_name', 'account_number', 'routing_number', 'account_type', 'is_active']:
            if field in data:
                update_fields.append(f"{field} = %s")
                values.append(data[field])
        
        if not update_fields:
            return jsonify({'success': False, 'error': 'No valid fields to update'}), 400
        
        values.extend([account_id, org_id])
        
        cursor.execute(
            f"UPDATE bank_accounts SET {', '.join(update_fields)} WHERE id = %s AND org_id = %s",
            values
        )
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Bank account updated successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@bank_accounts_bp.route('/bank-accounts/<int:account_id>', methods=['DELETE'])
@require_org
def delete_bank_account(account_id):
    """Delete a bank account"""
    claims = get_jwt()
    org_id = claims.get('org_id')
    role = claims.get('role')
    
    if not org_id:
        return jsonify({'success': False, 'error': 'Organization not found'}), 404
    
    if role != 'admin':
        return jsonify({'success': False, 'error': 'Permission denied. Only admins can delete bank accounts'}), 403
    
    conn = database_connection()
    if not conn:
        return jsonify({'success': False, 'error': 'Database unavailable'}), 500
    
    cursor = conn.cursor()
    try:
        # Check if account exists
        cursor.execute("SELECT id FROM bank_accounts WHERE id = %s AND org_id = %s", (account_id, org_id))
        if not cursor.fetchone():
            return jsonify({'success': False, 'error': 'Bank account not found'}), 404
        
        cursor.execute("DELETE FROM bank_accounts WHERE id = %s AND org_id = %s", (account_id, org_id))
        conn.commit()
        
        return jsonify({'success': True, 'message': 'Bank account deleted successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
