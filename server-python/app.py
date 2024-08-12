import os
import configparser
import logging
import subprocess
import time
import signal
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import jwt
from jwt import PyJWTError
from google.cloud import vision
from flask_cors import CORS
from PIL import Image  # Import Pillow

# Load configuration
config = configparser.ConfigParser()
config.read('/home/debian/irc/plugins-kiwiirc/kiwiirc-plugin-avatar-upload/server-python/config.ini')

# Set environment variables from config.ini
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config['DEFAULT']['GOOGLE_APPLICATION_CREDENTIALS']
JWT_KEY = config['DEFAULT']['JWT_KEY']

# Set up logging
log_dir = './logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
logging.basicConfig(filename=os.path.join(log_dir, 'app.log'), level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)

# Configuration
JWT_ALGORITHM = 'HS256'
THUMBNAIL_LARGE = 200
THUMBNAIL_SMALL = 80
AVATAR_DIR = '/home/debian/irc/AvatarsUsersFile'
ALLOWED_DOMAINS = ['https://web.redlatina.chat', 'https://chat.yagua.com.py']

def send_irc_report(message):
    logging.info(f"Sending report to IRC: {message}")
    try:
        with open('irc_messages.txt', 'a') as f:
            f.write(message + '\n')
    except Exception as e:
        logging.error(f"Failed to write message to IRC file: {e}")

# Initialize Google Cloud Vision client
client = vision.ImageAnnotatorClient()

# Check directories
def check_directory(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    if not os.access(dir_path, os.W_OK):
        raise PermissionError(f"Directory {dir_path} is not writable.")

check_directory(AVATAR_DIR)
check_directory(os.path.join(AVATAR_DIR, 'small'))
check_directory(os.path.join(AVATAR_DIR, 'large'))

@app.route('/upload', methods=['OPTIONS'])
def options():
    return '', 204

@app.route('/upload', methods=['POST'])
def upload():
    logging.debug(request.headers)  # Log request headers for debugging
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Token not provided"}), 401

    try:
        # Remove 'Bearer ' prefix from token string if present
        if token.startswith("Bearer "):
            token = token.split()[1]
        decoded_token = jwt.decode(token, JWT_KEY, algorithms=[JWT_ALGORITHM])
        account = decoded_token.get('account')
        logging.debug(decoded_token)  # Log decoded token for debugging
        if not account:
            raise jwt.DecodeError
    except (PyJWTError, IndexError) as e:
        logging.error(f"Token decode error: {e}")  # Log token decode error
        return jsonify({"error": "Invalid token"}), 401

    if 'image' not in request.files:
        logging.error("No image in request files")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['image']
    logging.debug(f"File name: {file.filename}")  # Log file name
    logging.debug(f"File content type: {file.content_type}")  # Log file content type
    if file.filename == '':
        logging.error("No selected file")
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        logging.error(f"File type not allowed: {file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'No extension'}")  # Log file type not allowed
        return jsonify({"error": "File type not allowed"}), 400

    # Use account name directly for filename
    filename = f"{account}.png"
    file_path = os.path.join(AVATAR_DIR, filename)
    file.save(file_path)

    # Check for explicit content
    content_flagged, response_message = detect_explicit_content(file_path, account)
    if content_flagged:
        os.remove(file_path)
        # Report to IRC
        send_irc_report(f"REPORTE: El usuario registrado --> {account} <-- intento subir una foto/imagen con contenido de tipo: nudes, violencia o pedofilia y ha sido denegado.")
        time.sleep(0.5)  # Add a short delay to ensure the messages are sent separately
        send_irc_report(f"Google content: {response_message}")

        return jsonify({"error": "Inappropriate content detected. Upload denied."})

    # Create thumbnails
    try:
        create_thumbnails(file_path, filename)
    except Exception as e:
        os.remove(file_path)
        logging.error(f"Failed to create thumbnails: {e}")
        return jsonify({"error": "Failed to create thumbnails"}), 500

    return jsonify({"message": "Image uploaded and resized successfully"}), 200

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' in filename:
        extension = filename.rsplit('.', 1)[1].lower()
        logging.debug(f"Checking file extension: {extension}")  # Log extension check
        return extension in ALLOWED_EXTENSIONS
    else:
        logging.error("No file extension found")  # Log no extension found
        return False

def detect_explicit_content(file_path, account):
    with open(file_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = client.safe_search_detection(image=image)
    safe_search = response.safe_search_annotation

    logging.debug(f"Google Vision Safe Search results for account {account}: {safe_search}")

    response_message = ""
    if safe_search.adult in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
        response_message = f"Adult content likelihood {safe_search.adult}"
        logging.warning(f"Explicit content detected for account {account}: {response_message}")
    elif safe_search.violence in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
        response_message = f"Violence content likelihood {safe_search.violence}"
        logging.warning(f"Explicit content detected for account {account}: {response_message}")
    else:
        logging.info(f"Content cleared for account {account}: No explicit content detected")
        response_message = "No explicit content detected"

    return safe_search.adult in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY] or \
           safe_search.violence in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY], response_message

def create_thumbnails(file_path, filename):
    img = Image.open(file_path)
    img_large = img.copy()
    img_large.thumbnail((THUMBNAIL_LARGE, THUMBNAIL_LARGE))
    img_large.save(os.path.join(AVATAR_DIR, 'large', filename), 'PNG')

    img_small = img.copy()
    img_small.thumbnail((THUMBNAIL_SMALL, THUMBNAIL_SMALL))
    img_small.save(os.path.join(AVATAR_DIR, 'small', filename), 'PNG')

if __name__ == '__main__':
    app.run(debug=True)
