import requests
import json

def send_email():
    url = "https://api.brevo.com/v3/smtp/email"

    # Your Brevo API key
    api_key = ""

    # Email data
    email_data = {
        "sender": {
            "name": "Fearless",
            "email": "hotdogbakedbeans@gmail.com"
        },
        "to": [
            {
                "email": "i.am.mbuguaa34@gmail.com",
                "name": "Recipient Name"
            }
        ],
        "subject": "Hello World",
        "htmlContent": "<html><head></head><body><p>Hello,</p><p>This is my first transactional email sent from Brevo.</p></body></html>"
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    # Send the email using the POST request
    response = requests.post(url, headers=headers, data=json.dumps(email_data))

    # Check the response
    if response.status_code == 201:
        print("Email sent successfully!")
    else:
        print(f"Error sending email: {response.status_code}, {response.text}")

# Call the function to send the email
send_email()
