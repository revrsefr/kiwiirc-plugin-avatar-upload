import os
import configparser
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

app = Flask(__name__)
CORS(app)

# Configuration
JWT_ALGORITHM = 'HS256'
THUMBNAIL_LARGE = 200
THUMBNAIL_SMALL = 80
AVATAR_DIR = '/home/debian/irc/AvatarsUsersFile'
ALLOWED_DOMAINS = ['https://webchat.t-chat.fr']

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
    print(request.headers)  # Log request headers for debugging
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Token not provided"}), 401

    try:
        # Remove 'Bearer ' prefix from token string if present
        if token.startswith("Bearer "):
            token = token.split()[1]
        decoded_token = jwt.decode(token, JWT_KEY, algorithms=[JWT_ALGORITHM])
        account = decoded_token.get('account')
        print(decoded_token)  # Log decoded token for debugging
        if not account:
            raise jwt.DecodeError
    except (PyJWTError, IndexError) as e:
        print(f"Token decode error: {e}")  # Log token decode error
        return jsonify({"error": "Invalid token"}), 401

    if 'image' not in request.files:
        print("No image in request files")
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['image']
    print(f"File name: {file.filename}")  # Log file name
    print(f"File content type: {file.content_type}")  # Log file content type
    if file.filename == '':
        print("No selected file")
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        print(f"File type not allowed: {file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'No extension'}")  # Log file type not allowed
        return jsonify({"error": "File type not allowed"}), 400

    filename = secure_filename(f"{account}.png")
    file_path = os.path.join(AVATAR_DIR, filename)
    file.save(file_path)

    # Check for explicit content
    if detect_explicit_content(file_path):
        os.remove(file_path)
        return jsonify({"error": "Inappropriate content detected. Upload denied."})

    # Create thumbnails
    try:
        create_thumbnails(file_path, filename)
    except Exception as e:
        os.remove(file_path)
        print(f"Failed to create thumbnails: {e}")
        return jsonify({"error": "Failed to create thumbnails"}), 500

    return jsonify({"message": "Image uploaded and resized successfully"}), 200

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' in filename:
        extension = filename.rsplit('.', 1)[1].lower()
        print(f"Checking file extension: {extension}")  # Log extension check
        return extension in ALLOWED_EXTENSIONS
    else:
        print("No file extension found")  # Log no extension found
        return False

def detect_explicit_content(file_path):
    with open(file_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = client.safe_search_detection(image=image)
    safe_search = response.safe_search_annotation

    if safe_search.adult == vision.Likelihood.LIKELY or \
       safe_search.adult == vision.Likelihood.VERY_LIKELY:
        return True
    return False

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
