from flask import Flask, request
from flask_socketio import SocketIO, emit
import whisper
import tempfile
import os
from transformers import pipeline
import sqlite3
from datetime import datetime

# -------------------------
# App Configuration
# -------------------------
app = Flask(
    __name__,
    static_folder="static",
    static_url_path=""
)
socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------------
# Database Helpers
# -------------------------
def get_db():
    conn = sqlite3.connect("meetings.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            date TEXT,
            duration TEXT,
            transcript TEXT,
            summary TEXT,
            actions TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# -------------------------
# Load Models
# -------------------------
whisper_model = whisper.load_model("base")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

audio_buffer = []

# -------------------------
# Routes (Pages)
# -------------------------
@app.route("/")
def dashboard():
    return app.send_static_file("dashboard.html")

@app.route("/recording")
def recording():
    return app.send_static_file("recording.html")

@app.route("/meetings")
def meetings_page():
    return app.send_static_file("meetings.html")

@app.route("/meeting/<int:id>")
def meeting_detail_page(id):
    return app.send_static_file("meeting_detail.html")

# -------------------------
# API — Fetch all meetings
# -------------------------
@app.route("/api/meetings")
def api_meetings():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM meetings ORDER BY id DESC"
    ).fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "title": r["title"],
            "date": r["date"],
            "duration": r["duration"],
            "summary": r["summary"],
            "actions": r["actions"].split("||") if r["actions"] else []
        }
        for r in rows
    ]

# -------------------------
# API — Fetch single meeting
# -------------------------
@app.route("/api/meeting/<int:id>")
def api_meeting(id):
    conn = get_db()
    r = conn.execute(
        "SELECT * FROM meetings WHERE id = ?",
        (id,)
    ).fetchone()
    conn.close()

    return {
        "id": r["id"],
        "title": r["title"],
        "date": r["date"],
        "duration": r["duration"],
        "summary": r["summary"],
        "transcript": r["transcript"],
        "actions": r["actions"].split("||") if r["actions"] else []
    }

# -------------------------
# API — Update title / summary
# -------------------------
@app.route("/api/meetings/update", methods=["POST"])
def update_meeting():
    data = request.json
    conn = get_db()
    conn.execute(
        f"UPDATE meetings SET {data['field']} = ? WHERE id = ?",
        (data["value"], data["id"])
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

# -------------------------
# API — Update action item
# -------------------------
@app.route("/api/meetings/update-action", methods=["POST"])
def update_action():
    data = request.json
    conn = get_db()

    row = conn.execute(
        "SELECT actions FROM meetings WHERE id = ?",
        (data["id"],)
    ).fetchone()

    actions = row["actions"].split("||") if row["actions"] else []
    actions[data["index"]] = data["value"]

    conn.execute(
        "UPDATE meetings SET actions = ? WHERE id = ?",
        ("||".join(actions), data["id"])
    )
    conn.commit()
    conn.close()

    return {"status": "ok"}

# -------------------------
# API — Delete meeting
# -------------------------
@app.route("/api/meetings/delete", methods=["POST"])
def delete_meeting():
    data = request.json
    conn = get_db()
    conn.execute("DELETE FROM meetings WHERE id = ?", (data["id"],))
    conn.commit()
    conn.close()
    return {"status": "deleted"}

# -------------------------
# Socket Events
# -------------------------
@socketio.on("audio_chunk")
def handle_audio(chunk):
    audio_buffer.append(chunk)

@socketio.on("end_meeting")
def end_meeting():
    global audio_buffer

    if not audio_buffer:
        emit("mom_generated", {"summary": "", "actions": []}, broadcast=True)
        return

    temp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)

    try:
        for c in audio_buffer:
            temp.write(c)
        temp.close()

        result = whisper_model.transcribe(temp.name)
        transcript = result["text"].strip()

        summary = summarizer(
            transcript,
            max_length=min(150, max(30, len(transcript.split()) // 2)),
            min_length=30,
            do_sample=False
        )[0]["summary_text"]

        actions = extract_action_items(transcript)

        conn = get_db()
        conn.execute("""
            INSERT INTO meetings (title, date, duration, transcript, summary, actions)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Meeting " + datetime.now().strftime("%d %b %Y %H:%M"),
            datetime.now().strftime("%d %b %Y"),
            "Auto",
            transcript,
            summary,
            "||".join(actions)
        ))
        conn.commit()
        conn.close()

        emit("mom_generated", {
            "summary": summary,
            "actions": actions
        }, broadcast=True)

    finally:
        os.unlink(temp.name)
        audio_buffer = []

# -------------------------
# Helpers
# -------------------------
def extract_action_items(text):
    sentences = text.split(".")
    return [
        s.strip()
        for s in sentences
        if any(k in s.lower() for k in ["will", "need to", "action", "assign"])
    ]

# -------------------------
# Run Server
# -------------------------
if __name__ == "__main__":
    socketio.run(app, debug=True)
