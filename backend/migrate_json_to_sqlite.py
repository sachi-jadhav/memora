import json
import sqlite3
import os

JSON_FILE = "data/meetings.json"
DB_FILE = "memora.db"

if not os.path.exists(JSON_FILE):
    print("No JSON file found.")
    exit()

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY,
    title TEXT,
    date TEXT,
    duration TEXT,
    transcript TEXT,
    summary TEXT,
    actions TEXT
)
""")

with open(JSON_FILE, "r") as f:
    meetings = json.load(f)

for m in meetings:
    cursor.execute("""
        INSERT OR IGNORE INTO meetings
        (id, title, date, duration, transcript, summary, actions)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        m["id"],
        m["title"],
        m["date"],
        m["duration"],
        m["transcript"],
        m["summary"],
        json.dumps(m["actions"])
    ))

conn.commit()
conn.close()

print("Migration complete. Meetings moved to SQLite.")
