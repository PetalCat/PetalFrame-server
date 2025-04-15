import sqlite3
import time
from uuid import uuid4
from modules.config import DB_PATH

def init_db():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		CREATE TABLE IF NOT EXISTS users (
			username TEXT PRIMARY KEY,
			password TEXT NOT NULL,
			is_admin INTEGER NOT NULL,
			avatar TEXT
		)
	""")
	c.execute("""
		CREATE TABLE IF NOT EXISTS videos (
			id TEXT PRIMARY KEY,
			username TEXT NOT NULL,
			filename TEXT NOT NULL,
			caption TEXT,
			timestamp INTEGER
		)
	""")
	conn.commit()
	conn.close()

def resolve_username_caseless(name: str) -> str | None:
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT username FROM users WHERE LOWER(username) = LOWER(?)", (name,))
	row = c.fetchone()
	conn.close()
	return row[0] if row else None

def user_exists(username: str, case_insensitive=False) -> bool:
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	query = "SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)" if case_insensitive else "SELECT 1 FROM users WHERE username=?"
	c.execute(query, (username,))
	exists = c.fetchone() is not None
	conn.close()
	return exists

def get_user(username: str, case_insensitive=False):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	query = "SELECT username, password, is_admin, avatar FROM users WHERE LOWER(username)=LOWER(?)" if case_insensitive else "SELECT password, is_admin, avatar FROM users WHERE username=?"
	c.execute(query, (username,))
	row = c.fetchone()
	conn.close()
	if row:
		return {
			"username": row[0] if case_insensitive else username,
			"hashed": row[1] if case_insensitive else row[0],
			"is_admin": bool(row[2] if case_insensitive else row[1]),
			"avatar": row[3] if case_insensitive else row[2]
		}
	return None

def add_user(username, password, is_admin):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", (username, password, int(is_admin)))
	conn.commit()
	conn.close()

def update_avatar(username, filename):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("UPDATE users SET avatar=? WHERE username=?", (filename, username))
	conn.commit()
	conn.close()

def list_users(include_admin=True):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	query = "SELECT username, is_admin, avatar FROM users" if include_admin else "SELECT username, avatar FROM users"
	c.execute(query)
	rows = c.fetchall()
	conn.close()
	return [
		{"username": r[0], "is_admin": bool(r[1]) if include_admin else None, "avatar": r[-1]}
		for r in rows
	]

def delete_user(username):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("DELETE FROM users WHERE username=?", (username,))
	c.execute("DELETE FROM videos WHERE username=?", (username,))
	conn.commit()
	conn.close()

def user_count():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT COUNT(*) FROM users")
	count = c.fetchone()[0]
	conn.close()
	return count

def track_upload(username, filename, caption):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("INSERT INTO videos (id, username, filename, caption, timestamp) VALUES (?, ?, ?, ?, ?)",
		(str(uuid4()), username, filename, caption, int(time.time())))
	conn.commit()
	conn.close()

def list_user_uploads(username):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT filename, caption, timestamp FROM videos WHERE username=?", (username,))
	rows = c.fetchall()
	conn.close()
	return [{"filename": r[0], "caption": r[1], "timestamp": r[2]} for r in rows]
