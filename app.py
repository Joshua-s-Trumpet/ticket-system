from flask import Flask, request, jsonify, render_template
import qrcode
from datetime import datetime
import os
from models import db, Ticket, ScanLog
from flasgger import Swagger  # Import Swagger

app = Flask(__name__)

# Initialize Swagger
swagger = Swagger(app)

# Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '/app/qr_codes'

db.init_app(app)

with app.app_context():
    db.create_all()

# Helper function to generate QR codes
def generate_qr_code(ticket_id):
    qr_data = f"http://127.0.0.1:5000/scan/{ticket_id}"  # Use localhost for ticket scanning
    file_name = f"{ticket_id}.png"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    qr_img = qrcode.make(qr_data)
    qr_img.save(file_path)
    return file_name

# Route 1: API to generate tickets and QR codes
@app.route('/generate', methods=['POST'])
def generate_ticket():
    """
    Generate a new ticket and QR code.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            phone:
              type: string
            ticket_type:
              type: string
              enum: [individual, group]
    responses:
      200:
        description: Ticket successfully generated
        schema:
          type: object
          properties:
            ticket_id:
              type: integer
            name:
              type: string
            phone:
              type: string
            ticket_type:
              type: string
            qr_code:
              type: string
    """
    data = request.json
    name = data['name']
    phone = data['phone']
    ticket_type = data['ticket_type']  # 'individual' or 'group'

    # Create new ticket in the database
    new_ticket = Ticket(name=name, phone=phone, ticket_type=ticket_type, scanned=False)
    db.session.add(new_ticket)
    db.session.commit()

    # Generate QR code
    qr_code_file = generate_qr_code(new_ticket.id)
    qr_code_url = f"/app/qr_codes/{qr_code_file}"  # Fixed the syntax error here

    return jsonify({
        'ticket_id': new_ticket.id,
        'name': new_ticket.name,
        'phone': new_ticket.phone,
        'ticket_type': new_ticket.ticket_type,
        'qr_code': qr_code_url
    })

# Route 2: API to scan QR codes and validate tickets
@app.route('/scan/<int:ticket_id>', methods=['GET'])
def scan_qr(ticket_id):
    """
    Scan a QR code and validate the ticket.
    ---
    parameters:
      - name: ticket_id
        in: path
        required: true
        type: integer
    responses:
      200:
        description: Ticket scanned successfully
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            message:
              type: string
              example: Ticket scanned successfully.
            ticket_id:
              type: integer
            name:
              type: string
            ticket_type:
              type: string
            scanned_at:
              type: string
              format: date-time
      400:
        description: Ticket has already been scanned
        schema:
          type: object
          properties:
            status:
              type: string
              example: error
            message:
              type: string
    """
    ticket = Ticket.query.get_or_404(ticket_id)

    # Check if the ticket has already been scanned
    if ticket.scanned:
        return jsonify({
            'status': 'error',
            'message': 'This ticket has already been scanned.',
            'ticket_id': ticket.id,
            'name': ticket.name,
            'ticket_type': ticket.ticket_type
        }), 400

    # Log the scan and mark the ticket as scanned
    scan_log = ScanLog(ticket_id=ticket.id, name=ticket.name, scanned_at=datetime.now())
    db.session.add(scan_log)

    ticket.scanned = True  # Mark the ticket as scanned
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': 'Ticket scanned successfully.',
        'ticket_id': ticket.id,
        'name': ticket.name,
        'ticket_type': ticket.ticket_type,
        'scanned_at': scan_log.scanned_at.isoformat()  # Return the time as a string
    })

# Route 3: Admin view for tickets and scans
@app.route('/admin', methods=['GET'])
def admin_dashboard():
    tickets = Ticket.query.all()
    scans = ScanLog.query.all()
    upload_folder = app.config['UPLOAD_FOLDER']  # Pass UPLOAD_FOLDER to template
    return render_template('admin.html', tickets=tickets, scans=scans, upload_folder=upload_folder)

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(host='0.0.0.0', port=5000, debug=True)