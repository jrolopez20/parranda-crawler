from flask import Flask, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import logging
import os
from dotenv import load_dotenv
    
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

app = Flask(__name__, static_folder='static')
CORS(app)

# Load environment variables from a .env file if present (optional)
try:
    
    logging.info("Loaded environment variables from .env (if present)")
except Exception:
    logging.debug("python-dotenv not installed or .env not found; using system env vars")

# Configuration - SET THESE AS ENVIRONMENT VARIABLES
MAILJET_API_KEY = os.environ.get('MAILJET_API_KEY', '')
MAILJET_SECRET_KEY = os.environ.get('MAILJET_SECRET_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'your_email@example.com')
SENDER_NAME = os.environ.get('SENDER_NAME', 'Product Crawler')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'recipient@example.com')

# Product configuration
CATALOG_URL = "https://cervezaparranda.com/catalog?sort=order"
PRODUCTS_API = "https://api.cervezaparranda.com/ms-auth/api/products/visibles"
PRODUCT_NAME = "Pallet Malta Guajira 330ml"

# File to track last status
STATUS_FILE = './static/product_status.txt'


def get_last_status():
    """Read last known status from file"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logging.error(f"Error reading status file: {e}")
    return None


def save_status(status):
    """Save current status to file"""
    try:
        with open(STATUS_FILE, 'w') as f:
            f.write(status)
    except Exception as e:
        logging.error(f"Error saving status file: {e}")


def find_product():
    """Query the products API and check if product has 'Próximamente' tag.
    """
    try:
        headers = {
            'dfl-shop-municipality': '09',
            'dfl-shop-region': '23',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
        }
        payload = {
            "filters": {
                "type": "TERM",
                "field": "rules.currencies",
                "value": "USD",
                "objectId": False,
                "isDate": False
            },
            "size": 24,
            "sort": {"order": "desc", "createdAt": "desc"}
        }

        resp = requests.post(PRODUCTS_API, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        items = resp.json()
        
        # Search for the product by name
        for item in items:            
            if PRODUCT_NAME.lower() == item["name"].lower():
                return item

        return None

    except requests.RequestException as e:
        logging.error(f"Error calling products API: {e}")
        return None
    except Exception as e:
        logging.error(f"Error parsing products API response: {e}")
        return None


def send_email():
    """Send email notification using Mailjet API"""
    try:
        url = "https://api.mailjet.com/v3.1/send"
        
        payload = {
            "Messages": [
                {
                    "From": {
                        "Email": SENDER_EMAIL,
                        "Name": SENDER_NAME
                    },
                    "To": [
                        {
                            "Email": RECIPIENT_EMAIL
                        },
                        {
                            "Email": "rfsosa12@gmail.com"
                        },
                    ],
                    "Subject": f" {PRODUCT_NAME} ya está disponible!",
                    "HTMLPart": f"""
                    <html>
                        <body style="font-family: Arial, sans-serif; padding: 20px;">
                            <h2 style="color: #2c3e50;">Han habilitado la Malta</h2>
                            <p><strong>{PRODUCT_NAME}</strong> ya está disponible en la tienda.</p>
                            <p><a href="{CATALOG_URL}" style="background-color: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Ver catálogo</a></p>
                            <p style="color: #7f8c8d; font-size: 12px;">Hora de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                        </body>
                    </html>
                    """
                }
            ]
        }
        
        response = requests.post(
            url,
            json=payload,
            auth=(MAILJET_API_KEY, MAILJET_SECRET_KEY),
            timeout=10
        )
        
        response.raise_for_status()
        logging.info("Email notification sent successfully via Mailjet")
        return True
        
    except Exception as e:
        logging.error(f"Error sending email via Mailjet: {e}")
        return False


@app.route('/')
def index():
    """Root endpoint"""
    return jsonify({
        'status': 'running',
        'product': PRODUCT_NAME,
        'url': PRODUCTS_API,
        'message': 'Product crawler is active. Use /check endpoint to run the crawler.',
        'email_configured': bool(MAILJET_API_KEY and MAILJET_SECRET_KEY)
    })


@app.route('/check')
def check_product():
    """Main endpoint to check product status"""
    logging.info(f"Checking product status at {datetime.now()}")
    
    try:
        message = ""
                
        # Find the product
        product = find_product()
        
        if not product:
            return jsonify({
                'status': 'error',
                'message': f"Product '{PRODUCT_NAME}' not found in API response",
                'timestamp': datetime.now().isoformat()
            }), 500
                
        # # Get last known status
        last_status = get_last_status()
        
        # Determine current status
        if not product["hasStock"]:
            current_status = 'unavailable'
            message = "Product still doesn't have stock."
            logging.info(message)
        else:
            current_status = 'available'
            message = "Product is AVAILABLE now!"
            logging.info(message)
            
            # Send email only if status changed from unavailable to available
            if last_status != 'available':
                email_sent = send_email()
                message += f" | Email sent: {email_sent}"

        # Save current status
        save_status(current_status)
        
        return jsonify({
            'status': 'success',
            'product_status': current_status,
            'message': message,
            'previous_status': last_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/status')
def get_status():
    """Get last known status"""
    last_status = get_last_status()
    return jsonify({
        'last_status': last_status,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)