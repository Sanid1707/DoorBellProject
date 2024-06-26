from flask import Flask, request, jsonify
import psycopg2
import os
import base64
import cv2
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
import face_recognition

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)

# Database connection details
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_PORT = os.getenv('DB_PORT')

def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT,
            sslmode='require'  # Ensure SSL is required
        )
        return conn
    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")
        return None

@app.route('/upload_image', methods=['POST'])
def upload_image():
    try:
        data = request.get_json()
        image_data = fix_base64_padding(data['image'])
        image_data = base64.b64decode(image_data)
        np_arr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # Process the image (e.g., face detection and embedding)
        face_embedding = get_face_embedding(image)

        first_name = data.get('first_name', 'Unknown')
        last_name = data.get('last_name', 'Unknown')

        conn = get_db_connection()
        if conn is None:
            return jsonify({"status": "error", "message": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO faces (first_name, last_name, face_embedding) VALUES (%s, %s, %s)",
            (first_name, last_name, psycopg2.Binary(face_embedding.tobytes()))
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "success"}), 201

    except Exception as e:
        app.logger.error(f"Error processing request: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/recognize_face', methods=['POST'])
def recognize_face():
    try:
        data = request.get_json()
        image_data = fix_base64_padding(data['image'])
        image_data = base64.b64decode(image_data)
        np_arr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # Extract face embedding from the image
        new_face_embedding = get_face_embedding(image)

        conn = get_db_connection()
        if conn is None:
            return jsonify({"status": "error", "message": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT id, first_name, last_name, face_embedding FROM faces")
        faces = cursor.fetchall()

        for face in faces:
            stored_embedding = np.frombuffer(face[3], dtype=np.float64)
            distance = np.linalg.norm(stored_embedding - new_face_embedding)
            
            if distance < 0.6:  # Threshold for recognizing a face (can be adjusted)
                return jsonify({
                    "status": "success",
                    "id": face[0],
                    "first_name": face[1],
                    "last_name": face[2]
                }), 200
        
        return jsonify({"status": "not found"}), 404

    except Exception as e:
        app.logger.error(f"Error recognizing face: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/faces', methods=['GET'])
def get_faces():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"status": "error", "message": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT id, first_name, last_name, timestamp FROM faces")
        faces = cursor.fetchall()
        cursor.close()
        conn.close()

        faces_list = []
        for face in faces:
            faces_list.append({
                "id": face[0],
                "first_name": face[1],
                "last_name": face[2],
                "timestamp": face[3].isoformat()
            })

        return jsonify(faces_list), 200

    except Exception as e:
        app.logger.error(f"Error fetching data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def get_face_embedding(image):
    # Extract face embeddings using face_recognition library
    face_locations = face_recognition.face_locations(image)
    face_encodings = face_recognition.face_encodings(image, face_locations)
    
    if face_encodings:
        return face_encodings[0]
    else:
        raise ValueError("No face found in the image")

def fix_base64_padding(base64_string):
    return base64_string + '==='[:len(base64_string) % 4]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
