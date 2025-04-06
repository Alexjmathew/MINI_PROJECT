from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
import os
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# Initialize Firebase
cred = credentials.Certificate('firebase.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Configure Gemini API
genai.configure(api_key=os.getenv("API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')


def clean_gemini_output(text: str) -> str:
    """Enhanced cleaning and formatting for Gemini's output"""
    # Remove unwanted markdown symbols
    text = re.sub(r'[*#_]{2,}', '', text)  # Remove excessive *, #, _
    text = re.sub(r'\\`', '`', text)  # Fix escaped backticks

    # Convert markdown to HTML with proper alignment
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)  # Bold
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)  # Italic
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)  # Code

    # Improve text alignment and spacing
    text = re.sub(r'\n{3,}', '\n\n', text)  # Limit consecutive newlines
    text = re.sub(r'\n', '<br>', text)  # Convert single newlines to breaks
    text = re.sub(r'<br>{2,}', '<br><br>', text)  # Normalize line breaks

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('chatbot'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            user_ref = db.collection('users').document(username)
            user = user_ref.get()

            if user.exists and user.to_dict().get('password') == password:
                session['username'] = username
                return redirect(url_for('chatbot'))
            else:
                return render_template('login.html', error="Invalid credentials")

        except Exception as e:
            return render_template('login.html', error=str(e))

    return render_template('login.html')


@app.route('/chatbot')
def chatbot():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('chatbot.html')


@app.route('/api/chat', methods=['POST'])
def chat_api():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()

        if not user_message:
            return jsonify({'success': False, 'error': 'Empty message'}), 400

        # Get user data from Firebase
        user_ref = db.collection('users').document(session['username'])
        user_data = user_ref.get().to_dict() or {}

        # Build context
        context = f"""You are PhysioBot, an AI physiotherapy assistant.
        Respond with clean, well-formatted text without markdown symbols.
        User Profile:
        - Name: {session['username']}
        - Age: {user_data.get('age', 'N/A')}
        - Height: {user_data.get('height', 'N/A')}
        - Weight: {user_data.get('weight', 'N/A')}"""

        # Generate and clean response
        response = model.generate_content(f"{context}\n\nUser: {user_message}")
        cleaned_response = clean_gemini_output(response.text)

        return jsonify({
            'success': True,
            'response': cleaned_response
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }), 500


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)