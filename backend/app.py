from flask import Flask, jsonify, send_from_directory, request, redirect, session
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from transformers import pipeline
import whisper
import tempfile
import os
from datetime import datetime

# ---------------- APP ----------------
app = Flask(__name__, static_folder="static")
app.secret_key = "dev-secret-key"

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///memora.db")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)


# ---------------- MODELS ----------------
class Meeting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    date = db.Column(db.String(100))
    duration = db.Column(db.String(20))
    transcript = db.Column(db.Text)
    summary = db.Column(db.Text)

class ActionItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meeting_id = db.Column(db.Integer, db.ForeignKey("meeting.id"))
    text = db.Column(db.String(300))

# ---------------- INIT ----------------
with app.app_context():
    db.create_all()

whisper_model = whisper.load_model("base")
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# ---------------- AUTH HELPERS ----------------
def login_required():
    return session.get("logged_in") is True

# ---------------- ROUTES ----------------
@app.route("/")
def login():
    return send_from_directory("static", "login.html")

@app.route("/signup")
def signup():
    return send_from_directory("static", "signup.html")

@app.route("/reset")
def reset():
    return send_from_directory("static", "reset.html")

@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect("/")
    return send_from_directory("static", "dashboard.html")

@app.route("/recording")
def recording():
    if not login_required():
        return redirect("/")
    return send_from_directory("static", "recording.html")

@app.route("/meetings")
def meetings():
    if not login_required():
        return redirect("/")
    return send_from_directory("static", "meetings.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- SOCKET STATE ----------------
full_transcript = []
meeting_start_time = None

# ---------------- HELPERS ----------------
def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def extract_action_items(text):
    keywords = ["will", "need to", "must", "should", "assign", "prepare", "submit", "review"]
    return [s.strip() for s in text.split(".") if any(k in s.lower() for k in keywords)]

# ---------------- SOCKET EVENTS ----------------
@socketio.on("audio_chunk")
def handle_audio(chunk):
    global meeting_start_time

    if meeting_start_time is None:
        meeting_start_time = datetime.now()

    temp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)

    try:
        temp.write(chunk)
        temp.close()

        result = whisper_model.transcribe(temp.name)
        text = result["text"].strip()

        if text:
            full_transcript.append(text)
            socketio.emit("transcript", {"text": text})

    finally:
        os.unlink(temp.name)

@socketio.on("end_meeting")
def end_meeting():
    global meeting_start_time, full_transcript

    transcript = " ".join(full_transcript)

    if len(transcript.split()) < 15:
        socketio.emit("mom_generated", {
            "summary": "Meeting was too short to generate a summary.",
            "actions": []
        })
        full_transcript = []
        meeting_start_time = None
        return

    summary = summarizer(transcript, max_length=120, min_length=40, do_sample=False)[0]["summary_text"]
    actions = extract_action_items(transcript)

    duration = format_duration(
        int((datetime.now() - meeting_start_time).total_seconds())
    )

    meeting = Meeting(
        title="Meeting " + datetime.now().strftime("%d %b %Y"),
        date=datetime.now().strftime("%d %b %Y, %I:%M %p"),
        duration=duration,
        transcript=transcript,
        summary=summary
    )

    db.session.add(meeting)
    db.session.commit()

    for a in actions:
        db.session.add(ActionItem(meeting_id=meeting.id, text=a))

    db.session.commit()

    socketio.emit("mom_generated", {
        "summary": summary,
        "actions": actions
    })

    full_transcript = []
    meeting_start_time = None

# ---------------- AUTH API ----------------
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    if data.get("email") and data.get("password"):
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

# ---------------- MEETINGS API ----------------
@app.route("/api/meetings")
def get_meetings():
    if not login_required():
        return jsonify([]), 401

    meetings = Meeting.query.order_by(Meeting.id.desc()).all()
    result = []

    for m in meetings:
        actions = ActionItem.query.filter_by(meeting_id=m.id).all()
        result.append({
            "id": m.id,
            "title": m.title,
            "date": m.date,
            "duration": m.duration,
            "summary": m.summary,
            "transcript": m.transcript,
            "actions": [a.text for a in actions]
        })

    return jsonify(result)

@app.route("/api/meetings/<int:meeting_id>", methods=["DELETE"])
def delete_meeting(meeting_id):
    ActionItem.query.filter_by(meeting_id=meeting_id).delete()
    Meeting.query.filter_by(id=meeting_id).delete()
    db.session.commit()
    return jsonify({"success": True})

# ---------------- RUN ----------------
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)



