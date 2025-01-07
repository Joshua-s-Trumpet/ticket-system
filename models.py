from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    ticket_type = db.Column(db.String(10), nullable=False)  # individual or group
    scanned = db.Column(db.Boolean, default=False)  # New column: True if scanned

class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    scanned_at = db.Column(db.DateTime, nullable=False)