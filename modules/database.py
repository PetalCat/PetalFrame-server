import sqlite3
import time
from uuid import uuid4
from modules.config import DB_PATH, QUEUE_DB_PATH

def init_db():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	# Users table
	c.execute("""
		CREATE TABLE IF NOT EXISTS users (
			username TEXT PRIMARY KEY,
			password TEXT NOT NULL,
			is_admin INTEGER NOT NULL,
			avatar TEXT
		)
	""")

	# Videos table
	c.execute("""
		CREATE TABLE IF NOT EXISTS videos (
			id TEXT PRIMARY KEY,
			username TEXT NOT NULL,
			filename TEXT NOT NULL,
			caption TEXT,
			timestamp INTEGER,
			date_taken INTEGER
		)
	""")

	# 🔥 NEW: Albums table
	c.execute("""
		CREATE TABLE IF NOT EXISTS albums (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			description TEXT,
			cover_filename TEXT,
			creator_username TEXT NOT NULL
		)
	""")

	# 🔥 NEW: Album Items linking table
	c.execute("""
		CREATE TABLE IF NOT EXISTS album_items (
			album_id TEXT,
			filename TEXT,
			PRIMARY KEY (album_id, filename),
			FOREIGN KEY (album_id) REFERENCES albums(id),
			FOREIGN KEY (filename) REFERENCES videos(filename)
		)
	""")

	conn.commit()
	conn.close()

def init_upload_queue_db():
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("""
		CREATE TABLE IF NOT EXISTS upload_queue (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			username TEXT NOT NULL,
			original_path TEXT NOT NULL,
			final_name TEXT NOT NULL,
			caption TEXT,
			is_video INTEGER NOT NULL,
			created_at INTEGER,
			status TEXT DEFAULT 'pending',
			retry_count INTEGER DEFAULT 0
		)
	""")
	conn.commit()
	conn.close()

def column_exists(conn, table: str, column: str) -> bool:
	c = conn.cursor()
	c.execute(f"PRAGMA table_info({table})")
	return any(row[1] == column for row in c.fetchall())

def table_exists(conn, table: str) -> bool:
	c = conn.cursor()
	c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
	return c.fetchone() is not None

def upgrade_main_db():
	conn = sqlite3.connect(DB_PATH)

	# Check and add missing column
	if not column_exists(conn, "videos", "date_taken"):
		print("[DB Upgrade] Adding date_taken column to videos...")
		conn.execute("ALTER TABLE videos ADD COLUMN date_taken INTEGER")

	# Albums
	if not table_exists(conn, "albums"):
		print("[DB Upgrade] Creating albums table...")
		conn.execute("""
			CREATE TABLE albums (
				id TEXT PRIMARY KEY,
				name TEXT NOT NULL,
				description TEXT,
				cover_filename TEXT,
				creator_username TEXT NOT NULL
			)
		""")

	if not table_exists(conn, "album_items"):
		print("[DB Upgrade] Creating album_items table...")
		conn.execute("""
			CREATE TABLE album_items (
				album_id TEXT,
				filename TEXT,
				PRIMARY KEY (album_id, filename),
				FOREIGN KEY (album_id) REFERENCES albums(id),
				FOREIGN KEY (filename) REFERENCES videos(filename)
			)
		""")

	conn.commit()
	conn.close()


def upgrade_queue_db():
	conn = sqlite3.connect(QUEUE_DB_PATH)

	if not table_exists(conn, "upload_queue"):
		print("[DB Upgrade] Creating upload_queue table...")
		conn.execute("""
			CREATE TABLE upload_queue (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				username TEXT NOT NULL,
				original_path TEXT NOT NULL,
				final_name TEXT NOT NULL,
				caption TEXT,
				is_video INTEGER NOT NULL,
				created_at INTEGER
			)
		""")

	else:
		if not column_exists(conn, "upload_queue", "status"):
			print("[DB Upgrade] Adding status column to upload_queue...")
			conn.execute("ALTER TABLE upload_queue ADD COLUMN status TEXT DEFAULT 'pending'")

		if not column_exists(conn, "upload_queue", "retry_count"):
			print("[DB Upgrade] Adding retry_count column to upload_queue...")
			conn.execute("ALTER TABLE upload_queue ADD COLUMN retry_count INTEGER DEFAULT 0")

	conn.commit()
	conn.close()


def add_date_taken_column():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	try:
		c.execute("ALTER TABLE videos ADD COLUMN date_taken INTEGER")
	except sqlite3.OperationalError as e:
		if "duplicate column" not in str(e).lower():
			raise
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

def track_upload(username, filename, caption, date_taken=None):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		INSERT INTO videos (id, username, filename, caption, timestamp, date_taken)
		VALUES (?, ?, ?, ?, ?, ?)
	""", (
		str(uuid4()),
		username,
		filename,
		caption,
		int(time.time()),
		int(date_taken) if date_taken else None
	))
	conn.commit()
	conn.close()

def list_user_uploads(username):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT filename, caption, timestamp, date_taken FROM videos WHERE username=?", (username,))
	rows = c.fetchall()
	conn.close()
	return [
		{
			"filename": r[0],
			"caption": r[1],
			"timestamp": r[2],
			"date_taken": r[3],
		}
		for r in rows
	]
