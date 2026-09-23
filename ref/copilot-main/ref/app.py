import os
import uuid
import traceback
import asyncio
import time
import subprocess
import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import edge_tts

from dotenv import load_dotenv

from google.adk.runners import Runner, InMemorySessionService, types

# Load environment variables from a local .env (if present)
load_dotenv()

# -------------------------
# IMPORT YOUR AGENTS
# -------------------------
from chatbot_agent import root_agent
from Report_Agent import root_agent as report_agent

# -------------------------
# Flask setup
# -------------------------
app = Flask(__name__, static_folder='frontend/public', static_url_path='/static')
CORS(app)

# -------------------------
# Folders
# -------------------------
AUDIO_FOLDER = "frontend/public/tts_audio"
UPLOAD_FOLDER = "frontend/public/uploads"

os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -------------------------
# ADK Setup
# -------------------------
APP_NAME = "medical_chatbot"

session_service = InMemorySessionService()

chat_runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service
)

report_runner = Runner(
    agent=report_agent,
    app_name=APP_NAME,
    session_service=session_service
)

Content = types.Content
Part = types.Part

# -------------------------
# SESSION STORE
# -------------------------
USER_SESSIONS = {}

def get_or_create_session(user_id: str):
    if user_id in USER_SESSIONS:
        return USER_SESSIONS[user_id]

    print("Creating session for:", user_id)

    async def _create():
        return await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id
        )

    session = asyncio.run(_create())
    USER_SESSIONS[user_id] = session.id
    return session.id

# -------------------------
# Edge TTS
# -------------------------
async def generate_tts(text, output_path):
    communicate = edge_tts.Communicate(
        text=text,
        voice="en-US-AriaNeural",
        rate="+0%",
        pitch="+0Hz"
    )
    await communicate.save(output_path)

# -------------------------
# STATIC FILES
# -------------------------
@app.route('/')
def index():
    return "Backend is running. Use frontend to interact."

@app.route('/style.css')
def serve_css():
    return send_from_directory('static', 'style.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('static', 'script.js')

@app.route('/tts_audio/<filename>')
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# -------------------------
# SAFE RUNNER
# -------------------------
def safe_run(runner, user_id, session_id, content, retries=3):
    for _ in range(retries):
        try:
            return runner.run(
                user_id=user_id,
                session_id=session_id,
                new_message=content
            )
        except Exception as e:
            print("LLM busy, retrying...", e)
            time.sleep(2)
    raise Exception("LLM overloaded")

# -------------------------
# CHAT ENDPOINT
# -------------------------
@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        user_id = data.get('user_id', 'default_user')

        session_id = get_or_create_session(user_id)

        content = Content(parts=[Part(text=user_message)])

        final_text = ""

        events = safe_run(chat_runner, user_id, session_id, content)

        for event in events:
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text = part.text

        if not final_text:
            final_text = "The AI is currently busy. Please try again."

        audio_file = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(AUDIO_FOLDER, audio_file)

        asyncio.run(generate_tts(final_text, audio_path))

        return jsonify({
            "success": True,
            "response": final_text,
            "audio_url": f"/tts_audio/{audio_file}"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------
# RESET CHAT SESSION
# -------------------------
@app.route('/api/reset', methods=['POST'])
def reset_chat():
    """
    Clears the stored session_id for a user so the next /api/chat
    call starts a fresh conversation context.
    """
    try:
        data = request.json or {}
        user_id = data.get('user_id', 'default_user')
        if user_id in USER_SESSIONS:
            del USER_SESSIONS[user_id]
        # Create a new session immediately so clients can confirm reset worked
        new_session_id = get_or_create_session(user_id)
        return jsonify({"success": True, "user_id": user_id, "session_id": new_session_id})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# -------------------------
# REPORT ENDPOINT
# -------------------------
@app.route('/api/report', methods=['POST'])
def analyze_report():
    try:
        if "image" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["image"]

        filename = f"{uuid.uuid4()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        user_id = "report_user"
        session_id = get_or_create_session(user_id)

        print("Saved report:", filepath)

        # 🔥 ONLY PASS FILE PATH — AGENT HANDLES EVERYTHING
        content = Content(parts=[
            Part(text=f"""
A medical report or scan is available at this file path:

{filepath}

Open it, analyze it, and explain the findings in simple patient language.
Warn clearly if something is dangerous.
""")
        ])

        final_text = ""

        events = safe_run(report_runner, user_id, session_id, content)

        for event in events:
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_text = part.text

        if not final_text:
            final_text = "Unable to analyze the report."

        audio_file = f"{uuid.uuid4()}_report.mp3"
        audio_path = os.path.join(AUDIO_FOLDER, audio_file)

        asyncio.run(generate_tts(final_text, audio_path))

        return jsonify({
            "success": True,
            "analysis": final_text,
            "audio_url": f"/tts_audio/{audio_file}",
            "image_url": f"/uploads/{filename}"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def start_location_server():
    """Starts the MCP location server in a separate process."""
    try:
        server_path = os.path.join("chatbot_agent", "location", "mcp_server.py")
        print(f"Starting location server: {server_path}")
        # Use the same python executable to run uvicorn
        # We assume uvicorn is installed in the environment
        subprocess.Popen([
            sys.executable, "-m", "uvicorn", 
            "chatbot_agent.location.mcp_server:app", 
            "--port", "7001", "--host", "127.0.0.1"
        ])
        print("Location server started on port 7001")
    except Exception as e:
        print(f"Failed to start location server: {e}")

# -------------------------
# MAIN
# -------------------------
if __name__ == '__main__':
    start_location_server()
    app.run(debug=True, port=5000, use_reloader=False)
