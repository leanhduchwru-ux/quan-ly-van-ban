import sqlite3
import json
import uuid
import datetime

DB_FILE = 'local_db.sqlite3'

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Crawler Sessions
    c.execute('''CREATE TABLE IF NOT EXISTS crawler_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        system TEXT UNIQUE,
        cookies TEXT,
        token TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Documents
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        system_source TEXT,
        type TEXT,
        document_no TEXT,
        summary TEXT,
        content TEXT,
        attachments TEXT,
        issued_date DATETIME,
        received_date DATETIME,
        deadline DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tasks
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        document_id TEXT,
        assignee TEXT,
        status TEXT,
        progress INTEGER DEFAULT 0,
        deadline DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(document_id) REFERENCES documents(id)
    )''')
    
    # App Stats for raw counts
    c.execute('''CREATE TABLE IF NOT EXISTS app_stats (
        key TEXT PRIMARY KEY,
        value INTEGER
    )''')
    
    # Document Relations
    c.execute('''CREATE TABLE IF NOT EXISTS document_relations (
        id TEXT PRIMARY KEY,
        incoming_id TEXT,
        outgoing_id TEXT,
        match_status TEXT,
        FOREIGN KEY(incoming_id) REFERENCES documents(id),
        FOREIGN KEY(outgoing_id) REFERENCES documents(id)
    )''')
    conn.commit()
    conn.close()

# Initialize DB
init_db()

def get_session(system_key):
    conn = get_connection()
    row = conn.execute("SELECT * FROM crawler_sessions WHERE system = ?", (system_key,)).fetchone()
    conn.close()
    return row

def save_session(system_key, cookies):
    conn = get_connection()
    cookies_str = json.dumps(cookies)
    row = conn.execute("SELECT id FROM crawler_sessions WHERE system = ?", (system_key,)).fetchone()
    if row:
        conn.execute("UPDATE crawler_sessions SET cookies = ?, updated_at = CURRENT_TIMESTAMP WHERE system = ?", (cookies_str, system_key))
    else:
        conn.execute("INSERT INTO crawler_sessions (system, cookies) VALUES (?, ?)", (system_key, cookies_str))
    conn.commit()
    conn.close()
