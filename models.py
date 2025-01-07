# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    ticket_type = db.Column(db.String(10), nullable=False)
    scanned = db.Column(db.Boolean, default=False)
    payment_reference = db.Column(db.String(100), unique=True)
    payment_status = db.Column(db.String(20), default='pending')
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    scanned_at = db.Column(db.DateTime, nullable=False)