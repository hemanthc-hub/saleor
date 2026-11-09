import datetime
import uuid
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ProductReview(db.Model):
    __tablename__ = 'product_reviews'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = db.Column(db.String(255), nullable=False, index=True)
    order_id = db.Column(db.String(255), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    delivery_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "order_id": self.order_id,
            "rating": self.rating,
            "comment": self.comment,
            "display_name": self.display_name,
            "delivery_date": self.delivery_date.isoformat() if self.delivery_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_approved": self.is_approved
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    action_type = db.Column(db.String(100), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False)
    records_processed = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    error_details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "action_type": self.action_type,
            "status": self.status,
            "records_processed": self.records_processed,
            "records_failed": self.records_failed,
            "error_details": self.error_details,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class EmailLog(db.Model):
    __tablename__ = 'email_logs'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = db.Column(db.String(255), nullable=True, index=True)
    order_number = db.Column(db.String(100), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False, index=True)
    email_type = db.Column(db.String(50), nullable=False)  # ORDER_RECEIPT, REVIEW_REQUEST, TEST_EMAIL
    subject = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="SENT")  # SENT, FAILED
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "order_id": self.order_id,
            "order_number": self.order_number,
            "recipient_email": self.recipient_email,
            "email_type": self.email_type,
            "subject": self.subject,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class CourierSLA(db.Model):
    __tablename__ = 'courier_slas'

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    courier_name = db.Column(db.String(100), nullable=False)  # e.g. "Bluedart Air Express", "Delhivery Surface", "DTDC Standard"
    zone_name = db.Column(db.String(100), nullable=False)     # e.g. "Bengaluru Local", "Karnataka & South", "Pan-India Metro"
    pincode_prefixes = db.Column(db.Text, nullable=False, default="*")  # e.g. "560, 561, 562" or "*"
    transit_days = db.Column(db.Integer, nullable=False, default=2)     # business days
    base_price = db.Column(db.Float, nullable=False, default=70.0)      # base shipping rate in INR
    per_kg_price = db.Column(db.Float, nullable=False, default=30.0)    # additional rate per kg over 1kg
    cutoff_hour = db.Column(db.Integer, nullable=False, default=14)     # 24-hr format (e.g. 14 for 2 PM cutoff)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "courier_name": self.courier_name,
            "zone_name": self.zone_name,
            "pincode_prefixes": self.pincode_prefixes,
            "transit_days": self.transit_days,
            "base_price": self.base_price,
            "per_kg_price": self.per_kg_price,
            "cutoff_hour": self.cutoff_hour,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

