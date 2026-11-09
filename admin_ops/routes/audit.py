from flask import Blueprint, jsonify
from admin_ops.database import AuditLog

audit_bp = Blueprint('audit', __name__)

@audit_bp.route('/audit', methods=['GET'])
def get_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify({
        "success": True,
        "logs": [log.to_dict() for log in logs]
    })
