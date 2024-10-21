import gevent.monkey
gevent.monkey.patch_all()

from app import app, socketio

if __name__ == "__main__":
    socketio.run(app)
(venv) guht@jimploof-ubuntu-2vcpu-4gb:/var/www/resume$ cat app.py
import os
import logging
import json
import traceback
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from flask_mail import Mail, Message
from functools import wraps
import requests
from dotenv import load_dotenv
from threading import Thread
from weather_data import get_weather_info

# Gevent monkey patch
#import gevent
#from gevent import monkey
#monkey.patch_all()

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('GMAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('GMAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('GMAIL_USERNAME')

flask_mail = Mail(app)

# Set debug mode and API key
app.config['DEBUG'] = True
API_KEY = os.getenv('WEATHER_API_KEY')

# Log file configuration
log_file_path = '/var/www/resume/resume_app.log'
logging.basicConfig(filename=log_file_path, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

# Go backend URL configuration
go_backend_url = os.getenv('GO_BACKEND_URL', 'http://localhost:8080')

# Admin login required decorator
def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('chat_admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Chat admin login route
@app.route('/chat_admin_login', methods=['GET', 'POST'])
def chat_admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == os.getenv('ADMIN_USERNAME') and password == os.getenv('ADMIN_PASSWORD'):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('components/authentication/admin-chat-login.html', error='Invalid username or password')

    return render_template('components/authentication/admin-chat-login.html')

# Admin dashboard route
@app.route('/admin/dashboard')
@admin_login_required
def admin_dashboard():
    try:
        # Fetch queue information from the Go backend
        go_queues_url = f"{go_backend_url}/queues"
        app.logger.debug(f"Attempting to fetch queues from: {go_queues_url}")

        response = requests.get(go_queues_url)

        app.logger.debug(f"Go backend response status: {response.status_code}")
        app.logger.debug(f"Go backend response content: {response.text}")

        if response.status_code == 200:
            queues = response.json()
            queue_details = [{'name': queue, 'message_count': 0} for queue in queues]  # Set message count as 0 for now
            return render_template('components/pages/chat_admin_dashboard.html', queues=queue_details)
        else:
            app.logger.error(f"Failed to retrieve queues: {response.status_code} {response.text}")
            return render_template('components/pages/chat_admin_dashboard.html', error="Failed to retrieve queue list from Go backend.")

    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return render_template('components/pages/chat_admin_dashboard.html', error="An unexpected error occurred.")

@socketio.on('connect')
def handle_connect():
    app.logger.info("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info("Client disconnected")

@socketio.on('admin_response')
def handle_admin_response(data):
    session_id = data['sessionID']
    response_message = data['message']
    send_response_to_go_backend(session_id, response_message)

def send_response_to_go_backend(session_id, response_message):
    try:
        # Send the response message to the Go backend
        response_url = f"{go_backend_url}/admin/response/{session_id}"
        message_data = {
            "message": response_message,
            "sessionID": session_id
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(response_url, data=json.dumps(message_data), headers=headers)

        if response.status_code == 200:
            app.logger.info(f"Successfully sent response to session {session_id}")
        else:
            app.logger.error(f"Failed to send response to session {session_id}: {response.text}")
    except Exception as e:
        app.logger.error(f"Error while sending response to Go backend: {str(e)}")

# Main weather dashboard route
@app.route('/')
@app.route('/index')
def index():
    app.logger.info('Request Headers: %s', request.headers)

    lat = request.environ.get('X-GeoIP2-Latitude', '0')
    lon = request.environ.get('X-GeoIP2-Longitude', '0')

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        lat, lon = 0.0, 0.0

    weather_description, temperature, weather_code = get_weather_info(lat, lon, API_KEY)

    if weather_description is None or temperature is None or weather_code is None:
        weather_description = 'Unknown'
        temperature = 404
        weather_code = 1000

    background_image = f'weather_background_{str(weather_code)[0]}.png'

    return render_template('components/pages/landing.html',
                           weather_description=weather_description,
                           temperature=f'{temperature:.1f}',
                           weather_code=weather_code,
                           background_image=background_image,
                           geo_info={'latitude': lat, 'longitude': lon})

# Contact form submission route
@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        app.logger.info(f"Received form data: {request.form}")

        name = request.form.get('name', 'Not provided')
        email = request.form.get('email', 'Not provided')
        phone = request.form.get('phone', 'Not provided')
        company = request.form.get('company', 'Not provided')
        message = request.form.get('message', 'Not provided')

        lat = request.environ.get('X-GeoIP2-Latitude', 'Not available')
        lon = request.environ.get('X-GeoIP2-Longitude', 'Not available')
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)

        app.logger.info(f"Extracted form info: Name: {name}, Email: {email}, Phone: {phone}, Company: {company}")

        recipient_email = os.getenv('RECIPIENT_EMAIL')
        if not recipient_email:
            raise ValueError("RECIPIENT_EMAIL is not set in the .env file")

        msg = Message("New Contact Form Submission", recipients=[recipient_email])
        msg.body = f"""Name: {name}
Email: {email}
Phone: {phone}
Company: {company}
Message: {message}

Geolocation Information:
IP Address: {ip_address}
Latitude: {lat}
Longitude: {lon}"""

        app.logger.info("Attempting to send email...")
        flask_mail.send(msg)

        app.logger.info("Email sent successfully")
        return jsonify({"success": True})

    except Exception as e:
        app.logger.error(f"Unexpected error sending email: {str(e)}")
        app.logger.error(f"Exception traceback: {traceback.format_exc()}")
        error_message = "An unexpected error occurred. Please try again later."
        return jsonify({"success": False, "error": error_message}), 500

if __name__ == '__main__':
#    socketio.run(app)
    pass
