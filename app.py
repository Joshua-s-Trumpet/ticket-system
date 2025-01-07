# app.py
from flask import Flask, request, jsonify, render_template, abort
import qrcode
from datetime import datetime
import os
import hmac
import hashlib
from functools import wraps
import json
from models import db, Ticket, ScanLog
from flasgger import Swagger, swag_from

app = Flask(__name__)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '/app/qr_codes'
app.config['PAYSTACK_SECRET_KEY'] = 'your_paystack_secret_key'

# Swagger Configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec',
            "route": '/apispec.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs"
}

swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Event Ticket System API",
        "description": "API for managing event tickets with Paystack integration",
        "version": "1.0.0",
        "contact": {
            "email": "your-email@example.com"
        }
    },
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "PaystackSignature": {
            "type": "apiKey",
            "name": "x-paystack-signature",
            "in": "header",
            "description": "Paystack webhook signature for request verification"
        }
    }
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

PAYSTACK_IPS = ['52.31.139.75', '52.49.173.169', '52.214.14.220']

db.init_app(app)

def verify_paystack_webhook(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        paystack_signature = request.headers.get('x-paystack-signature')
        if not paystack_signature:
            abort(400, description='No Paystack signature found')

        payload = request.get_data()
        calculated_signature = hmac.new(
            app.config['PAYSTACK_SECRET_KEY'].encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()

        if paystack_signature != calculated_signature:
            abort(400, description='Invalid signature')

        return f(*args, **kwargs)
    return decorated_function

def generate_qr_code(ticket_id, base_url):
    qr_data = {
        'ticket_id': ticket_id,
        'validation_url': f"{base_url}/scan/{ticket_id}"
    }
    
    file_name = f"{ticket_id}.png"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    
    qr_img = qrcode.make(json.dumps(qr_data))
    qr_img.save(file_path)
    return file_name

@app.route('/webhook/paystack', methods=['POST'])
@verify_paystack_webhook
@swag_from({
    'tags': ['Webhooks'],
    'description': 'Handle Paystack payment webhook events',
    'parameters': [
        {
            'name': 'x-paystack-signature',
            'in': 'header',
            'type': 'string',
            'required': True,
            'description': 'Paystack signature for webhook verification'
        },
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'event': {'type': 'string', 'example': 'charge.success'},
                    'data': {
                        'type': 'object',
                        'properties': {
                            'reference': {'type': 'string'},
                            'amount': {'type': 'integer'},
                            'customer': {
                                'type': 'object',
                                'properties': {
                                    'email': {'type': 'string'}
                                }
                            },
                            'metadata': {
                                'type': 'object',
                                'properties': {
                                    'customer_name': {'type': 'string'},
                                    'phone': {'type': 'string'},
                                    'ticket_type': {'type': 'string'}
                                }
                            }
                        }
                    }
                }
            }
        }
    ],
    'responses': {
        '200': {
            'description': 'Webhook processed successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'ticket_id': {'type': 'integer'}
                }
            }
        },
        '400': {
            'description': 'Invalid webhook signature or payload'
        }
    }
})
def paystack_webhook():
    event = request.get_json()
    
    if event.get('event') != 'charge.success':
        return jsonify({'status': 'ignored'}), 200
    
    data = event.get('data', {})
    metadata = data.get('metadata', {})
    
    ticket = Ticket(
        name=metadata.get('customer_name'),
        email=data.get('customer', {}).get('email'),
        phone=metadata.get('phone'),
        ticket_type=metadata.get('ticket_type', 'individual'),
        payment_reference=data.get('reference'),
        payment_status='paid',
        amount=data.get('amount')
    )
    
    db.session.add(ticket)
    db.session.commit()
    
    base_url = request.url_root.rstrip('/')
    generate_qr_code(ticket.id, base_url)
    
    return jsonify({'status': 'success', 'ticket_id': ticket.id}), 200

@app.route('/scan/<int:ticket_id>', methods=['GET'])
@swag_from({
    'tags': ['Tickets'],
    'description': 'Validate and scan a ticket',
    'parameters': [
        {
            'name': 'ticket_id',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'description': 'ID of the ticket to validate'
        }
    ],
    'responses': {
        '200': {
            'description': 'Ticket validated successfully',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'message': {'type': 'string'},
                    'ticket_details': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'integer'},
                            'name': {'type': 'string'},
                            'email': {'type': 'string'},
                            'ticket_type': {'type': 'string'},
                            'scanned_at': {'type': 'string', 'format': 'date-time'}
                        }
                    }
                }
            }
        },
        '400': {
            'description': 'Invalid ticket or already scanned',
            'schema': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'message': {'type': 'string'}
                }
            }
        },
        '404': {
            'description': 'Ticket not found'
        }
    }
})
def scan_qr(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    
    if ticket.payment_status != 'paid':
        return jsonify({
            'status': 'error',
            'message': 'Ticket payment not completed'
        }), 400

    if ticket.scanned:
        return jsonify({
            'status': 'error',
            'message': 'Ticket already used',
            'scan_details': {
                'ticket_id': ticket.id,
                'name': ticket.name,
                'ticket_type': ticket.ticket_type
            }
        }), 400

    scan_log = ScanLog(
        ticket_id=ticket.id,
        name=ticket.name,
        scanned_at=datetime.utcnow()
    )
    ticket.scanned = True
    
    db.session.add(scan_log)
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Ticket validated successfully',
        'ticket_details': {
            'id': ticket.id,
            'name': ticket.name,
            'email': ticket.email,
            'ticket_type': ticket.ticket_type,
            'scanned_at': scan_log.scanned_at.isoformat()
        }
    })

@app.route('/admin', methods=['GET'])
@swag_from({
    'tags': ['Admin'],
    'description': 'Admin dashboard for viewing tickets and scan logs',
    'responses': {
        '200': {
            'description': 'Admin dashboard HTML page'
        }
    }
})
def admin_dashboard():
    tickets = Ticket.query.all()
    scans = ScanLog.query.all()
    return render_template('admin.html', tickets=tickets, scans=scans, upload_folder=app.config['UPLOAD_FOLDER'])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0', port=5000)