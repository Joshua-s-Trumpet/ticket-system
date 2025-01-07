from flask import Flask, request, jsonify, render_template, abort
import qrcode
from datetime import datetime
import os
import hmac
import hashlib
from functools import wraps
import json
import logging
import requests
from models import db, Ticket, ScanLog
from flasgger import Swagger, swag_from
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Email configuration
BREVO_API_KEY = "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"

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '/app/qr_codes'
app.config['PAYSTACK_SECRET_KEY'] = 'sk_test_1a0343ea53d6861bafba36c8cfd73be700a500fa'

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
        "description": "API for managing event tickets with Paystack payment integration and QR code scanning capabilities",
        "version": "1.0.0",
        "contact": {
            "email": "baraka@fearless.com",
            "name": "API Support Team"
        },
        "license": {
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        }
    }, 
    "schemes": ["http", "https"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "securityDefinitions": {
        "PaystackSignature": {
            "type": "apiKey",
            "name": "x-paystack-signature",
            "in": "header",
            "description": "Paystack webhook signature for request verification"
        }
    },
    "tags": [
        {
            "name": "Webhooks",
            "description": "Payment webhook endpoints for Paystack integration"
        },
        {
            "name": "Tickets",
            "description": "Ticket validation and scanning operations"
        },
        {
            "name": "Admin",
            "description": "Administrative dashboard and management functions"
        }
    ],
    "definitions": {
        "Ticket": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "Unique identifier for the ticket"
                },
                "name": {
                    "type": "string",
                    "description": "Name of the ticket holder"
                },
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email address of the ticket holder"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number of the ticket holder"
                },
                "ticket_type": {
                    "type": "string",
                    "enum": ["individual", "group", "vip"],
                    "description": "Type of ticket purchased"
                },
                "payment_reference": {
                    "type": "string",
                    "description": "Unique payment reference from Paystack"
                },
                "payment_status": {
                    "type": "string",
                    "enum": ["pending", "paid", "failed"],
                    "description": "Current status of the payment"
                },
                "scanned": {
                    "type": "boolean",
                    "description": "Whether the ticket has been scanned"
                },
                "created_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Timestamp when the ticket was created"
                }
            }
        },
        "ScanLog": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "Unique identifier for the scan log"
                },
                "ticket_id": {
                    "type": "integer",
                    "description": "Reference to the scanned ticket"
                },
                "name": {
                    "type": "string",
                    "description": "Name of the ticket holder"
                },
                "scanned_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Timestamp when the ticket was scanned"
                }
            }
        }
    }
}

def paystack_webhook_spec():
    return {
        'tags': ['Webhooks'],
        'description': 'Handle Paystack payment webhook events for ticket creation',
        'parameters': [{
            'name': 'x-paystack-signature',
            'in': 'header',
            'type': 'string',
            'required': True,
            'description': 'HMAC SHA512 signature of the request body'
        }],
        'requestBody': {
            'description': 'Paystack webhook event payload',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'event': {'type': 'string'},
                            'data': {'type': 'object'}
                        }
                    }
                }
            }
        },
        'responses': {
            '200': {
                'description': 'Ticket created successfully',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string'},
                        'message': {'type': 'string'},
                        'ticket_id': {'type': 'integer'},
                        'qr_code': {'type': 'string'}
                    }
                }
            },
            '400': {
                'description': 'Invalid request or validation error',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string'},
                        'message': {'type': 'string'},
                        'errors': {'type': 'array', 'items': {'type': 'string'}}
                    }
                }
            }
        }
    }

def scan_qr_spec():
    return {
        'tags': ['Tickets'],
        'description': 'Validate and scan a ticket QR code',
        'parameters': [{
            'name': 'ticket_id',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'description': 'ID of the ticket to scan'
        }],
        'responses': {
            '200': {
                'description': 'Ticket validated successfully',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string'},
                        'message': {'type': 'string'},
                        'ticket_details': {'$ref': '#/definitions/Ticket'}
                    }
                }
            },
            '400': {
                'description': 'Invalid ticket or already scanned',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'status': {'type': 'string'},
                        'message': {'type': 'string'},
                        'scan_details': {'$ref': '#/definitions/ScanLog'}
                    }
                }
            }
        }
    }


swagger = Swagger(app, config=swagger_config, template=swagger_template)

PAYSTACK_IPS = ['52.31.139.75', '52.49.173.169', '52.214.14.220']

db.init_app(app)

def verify_paystack_webhook(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            paystack_signature = request.headers.get('x-paystack-signature')
            if not paystack_signature:
                logger.error("Missing Paystack signature")
                abort(400, description='No Paystack signature found')

            payload = request.get_data()
            calculated_signature = hmac.new(
                app.config['PAYSTACK_SECRET_KEY'].encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            if paystack_signature != calculated_signature:
                logger.error("Invalid Paystack signature")
                abort(400, description='Invalid signature')

            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Webhook verification error: {str(e)}")
            abort(400, description='Webhook verification failed')
    return decorated_function

def generate_qr_code(ticket_id, base_url):
    """Generate QR code for ticket"""
    try:
        qr_data = {
            'ticket_id': ticket_id,
            'validation_url': f"{base_url}/scan/{ticket_id}"
        }
        
        file_name = f"{ticket_id}.png"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        
        qr_img = qrcode.make(json.dumps(qr_data))
        qr_img.save(file_path)
        return file_name
    except Exception as e:
        logger.error(f"QR code generation error: {str(e)}")
        raise

def validate_ticket_data(data, metadata, customer):
    """Validate ticket data from Paystack webhook"""
    errors = []
    
    # Required fields validation
    if not customer.get('email'):
        errors.append("Customer email is required")
    
    if not data.get('amount'):
        errors.append("Payment amount is required")
        
    if not data.get('reference'):
        errors.append("Payment reference is required")
        
    return errors

# Send email using Brevo API
def send_email_via_brevo_with_attachment(subject, body, customer_email, attachment_data, filename):
    url = "https://api.brevo.com/v3/smtp/email"

    email_data = {
        "sender": {
            "name": "Fearless",
            "email": "hotdogbakedbeans@gmail.com"
        },
        "to": [
            {
                "email": customer_email,
                "name": customer_email.split('@')[0]
            }
        ],
        "subject": subject,
        "htmlContent": body,
        "attachment": [
            {
                "content": base64.b64encode(attachment_data).decode('utf-8'),
                "name": filename,
                "type": "image/png"
            }
        ]
    }

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    response = requests.post(url, headers=headers, data=json.dumps(email_data))

    if response.status_code == 201:
        logger.info(f"Email sent successfully to {customer_email}")
    else:
        logger.error(f"Error sending email to {customer_email}: {response.status_code}, {response.text}")   

# Send QR code via email
def send_qr_code_via_email(ticket, qr_filename):
    """Send the generated QR code to the email address of the ticket holder using Brevo API"""
    try:
        subject = "Your Event Ticket"
        body = f"Hello {ticket.name},\n\nYour ticket has been generated. Please find the attached QR code to validate your entry."
        
        # Ensure the folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Read the QR code file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], qr_filename)
        with open(file_path, 'rb') as f:
            attachment_data = f.read()
        
        # Send email with QR code as an attachment
        send_email_via_brevo_with_attachment(subject, body, ticket.email, attachment_data, qr_filename)

        logger.info(f"Sent email to {ticket.email} with QR code")

    except Exception as e:
        logger.error(f"Error sending email to {ticket.email}: {str(e)}")
        
@app.route('/webhook/paystack', methods=['POST'])
@verify_paystack_webhook
@swag_from(paystack_webhook_spec())
def paystack_webhook():
    try:
        event = request.get_json()
        logger.info(f"Received webhook event: {event.get('event')}")
        
        if event.get('event') != 'charge.success':
            return jsonify({'status': 'ignored', 'message': 'Not a charge.success event'}), 200
        
        data = event.get('data', {})
        metadata = data.get('metadata', {})
        customer = data.get('customer', {})
        
        # Validate required data
        validation_errors = validate_ticket_data(data, metadata, customer)
        if validation_errors:
            logger.error(f"Validation errors: {validation_errors}")
            return jsonify({
                'status': 'error',
                'message': 'Validation failed',
                'errors': validation_errors
            }), 400
        
        # Extract customer details with fallbacks
        name = (
            metadata.get('customer_name') or 
            metadata.get('name') or 
            f"{customer.get('first_name', '')} {customer.get('last_name', '')}" or
            customer.get('email').split('@')[0]  
        ).strip()
        
        phone = metadata.get('phone') or customer.get('phone') or 'N/A'
        
        try:
            ticket = Ticket(
                name=name,
                email=customer['email'],
                phone=phone,
                ticket_type=metadata.get('ticket_type', 'individual'),
                payment_reference=data['reference'],
                payment_status='paid',
                amount=data['amount']
            )
            
            db.session.add(ticket)
            db.session.commit()
            
            # Generate QR code
            base_url = request.url_root.rstrip('/')
            qr_filename = generate_qr_code(ticket.id, base_url)
            
            # Send the QR code via email
            send_qr_code_via_email(ticket, qr_filename)
            
            logger.info(f"Successfully created ticket {ticket.id} for {customer['email']}")
            
            return jsonify({
                'status': 'success',
                'message': 'Ticket created successfully',
                'ticket_id': ticket.id,
                'qr_code': qr_filename
            }), 200
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to create ticket'
            }), 500
            
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to process webhook'
        }), 500

@app.route('/scan/<int:ticket_id>', methods=['GET'])
@swag_from(scan_qr_spec())
def scan_qr(ticket_id):
    try:
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
                    'ticket_type': ticket.ticket_type,
                    'scanned_at': ticket.scanlog[0].scanned_at.isoformat() if ticket.scanlog else None
                }
            }), 400

        try:
            scan_log = ScanLog(
                ticket_id=ticket.id,
                name=ticket.name,
                scanned_at=datetime.utcnow()
            )
            ticket.scanned = True
            
            db.session.add(scan_log)
            db.session.commit()
            
            logger.info(f"Successfully scanned ticket {ticket_id}")

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
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during scan: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': 'Failed to record scan'
            }), 500
            
    except Exception as e:
        logger.error(f"Scan processing error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to process scan'
        }), 500

@app.route('/admin', methods=['GET'])
@swag_from({
    'tags': ['Admin'],
    'description': 'Admin dashboard for viewing tickets and scan logs'
})
def admin_dashboard():
    try:
        tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
        scans = ScanLog.query.order_by(ScanLog.scanned_at.desc()).all()
        return render_template(
            'admin.html',
            tickets=tickets,
            scans=scans,
            upload_folder=app.config['UPLOAD_FOLDER']
        )
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load admin dashboard'
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        'status': 'error',
        'message': 'Resource not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    # Create upload folder if it doesn't exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Create database tables
    with app.app_context():
        db.create_all()
        
    app.run(host='0.0.0.0', port=5000)