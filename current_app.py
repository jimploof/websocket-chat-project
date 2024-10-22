# /var/www/socketio/app.py
import eventlet
eventlet.monkey_patch()

import os
import logging
import sys
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

# Enhanced logging setup
logging.basicConfig(
    filename='/var/www/socketio/socketio.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
)

# Also log to stderr for uWSGI
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(handler)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'
app.config['DEBUG'] = True

socketio = SocketIO(
    app,
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    cors_allowed_origins="*"
)

@app.route('/socket.io/test')
def test_client():
    app.logger.info(f'Test client accessed from {request.remote_addr}')
    try:
        return render_template('index.html')
    except Exception as e:
        app.logger.error(f'Error serving test client: {str(e)}')
        return str(e), 500

# Add a health check route
@app.route('/socket.io/health')
def health_check():
    return jsonify({'status': 'healthy'})

@app.errorhandler(Exception)
def handle_error(e):
    app.logger.error(f'Unhandled error: {str(e)}')
    return str(e), 500

@socketio.on_error()
def error_handler(e):
    app.logger.error(f'SocketIO error: {str(e)}')

@socketio.on('connect')
def handle_connect():
    app.logger.info(f'Client connected: {request.sid} from {request.remote_addr}')

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info(f'Client disconnected: {request.sid}')

@socketio.on('message')
def handle_message(data):
    app.logger.info(f'Received message from {request.sid}: {data}')
    try:
        socketio.emit('response', {'data': f'Server received: {data}'})
    except Exception as e:
        app.logger.error(f'Error sending response: {str(e)}')

if __name__ == '__main__':
    socketio.run(app)
