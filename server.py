import os
import shutil
import sqlite3
import time
import json
from uuid import uuid4
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from jose import JWTError, jwt

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
AVATAR_DIR = "avatars"
DB_PATH = "app.db"
CONFIG_PATH = "config.json"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# --- Config ---
def get_config():
	if not os.path.exists(CONFIG_PATH):
		default = {
			"signup_locked": False,
			"secret_key": os.urandom(32).hex()
		}
		with open(CONFIG_PATH, "w") as f:
			json.dump(default, f)
	return json.load(open(CONFIG_PATH))

def save_config(config):
	with open(CONFIG_PATH, "w") as f:
		json.dump(config, f)

config = get_config()
SECRET_KEY = config["secret_key"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 36000

# --- DB init ---
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
init_db()

# --- Helpers ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_user(username):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT password, is_admin, avatar FROM users WHERE username=?", (username,))
	row = c.fetchone()
	conn.close()
	if row:
		return {"hashed": row[0], "is_admin": bool(row[1]), "avatar": row[2]}
	return None

def user_exists(username):
	return get_user(username) is not None

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
	users = [
		{"username": row[0], "is_admin": bool(row[1]) if include_admin else None, "avatar": row[-1]}
		for row in c.fetchall()
	]
	conn.close()
	return users

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
	uploads = [{"filename": row[0], "caption": row[1], "timestamp": row[2]} for row in c.fetchall()]
	conn.close()
	return uploads

# --- Auth ---
def verify_password(plain, hashed):
	return pwd_context.verify(plain, hashed)

def hash_password(pw):
	return pwd_context.hash(pw)

def create_token(username: str):
	expire = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS
	return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		return payload.get("sub")
	except JWTError:
		return None

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

def require_admin(username: str = Depends(get_current_user)):
	user = get_user(username)
	if not user or not user["is_admin"]:
		raise HTTPException(status_code=403, detail="Admin only")
	return username

# --- Routes ---

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
	if user_exists(username):
		raise HTTPException(status_code=400, detail="Username taken")
	if get_config()["signup_locked"] and user_count() > 0:
		raise HTTPException(status_code=403, detail="Signups are locked")
	is_admin = user_count() == 0
	add_user(username, hash_password(password), is_admin)
	return {"msg": "User created", "is_admin": is_admin}

@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
	user = get_user(form.username)
	if not user or not verify_password(form.password, user["hashed"]):
		time.sleep(1)
		raise HTTPException(status_code=401, detail="Bad credentials")
	token = create_token(form.username)
	return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
def get_me(username: str = Depends(get_current_user)):
	user = get_user(username)
	return {
		"username": username,
		"is_admin": user["is_admin"],
		"avatar": user["avatar"]
	}

@app.post("/me/avatar")
async def upload_avatar(username: str = Depends(get_current_user), file: UploadFile = File(...)):
	if not file.content_type.startswith("image/"):
		raise HTTPException(status_code=400, detail="Only image files allowed")
	ext = os.path.splitext(file.filename)[-1]
	filename = f"{username}{ext}"
	save_path = os.path.join(AVATAR_DIR, filename)
	with open(save_path, "wb") as f:
		shutil.copyfileobj(file.file, f)
	update_avatar(username, filename)
	return {"avatar": filename}

@app.get("/avatar/{filename}")
def get_avatar(filename: str, token: str = Depends(oauth2_scheme)):
	if not filename:
		filename = "default-pfp.svg"
	file_path = os.path.join(AVATAR_DIR, filename)
	if os.path.exists(file_path):
		return FileResponse(file_path)
	default_path = os.path.join("src", "assets", "default-pfp.svg")
	if os.path.exists(default_path):
		return FileResponse(default_path, media_type="image/svg+xml")
	raise HTTPException(status_code=404, detail="Avatar not found")

@app.post("/upload")
async def upload_video(username: str = Depends(get_current_user), caption: str = Form(""), file: UploadFile = File(...)):
	if not file.content_type.startswith("video/"):
		raise HTTPException(status_code=400, detail="Only video files allowed")
	video_id = str(uuid4())
	ext = os.path.splitext(file.filename)[-1]
	filename = f"{video_id}{ext}"
	save_path = os.path.join(UPLOAD_DIR, filename)
	with open(save_path, "wb") as out_file:
		shutil.copyfileobj(file.file, out_file)
	track_upload(username, filename, caption.strip())
	return {"id": video_id, "filename": filename}

@app.get("/my_uploads")
def my_uploads(username: str = Depends(get_current_user)):
	return list_user_uploads(username)

# --- Admin ---

@app.get("/admin/signup_status")
def get_signup_status(_: str = Depends(require_admin)):
	return {"locked": get_config()["signup_locked"]}

@app.post("/admin/lock_signup")
def lock_signup(_: str = Depends(require_admin)):
	config = get_config()
	config["signup_locked"] = True
	save_config(config)
	return {"status": "locked"}

@app.post("/admin/unlock_signup")
def unlock_signup(_: str = Depends(require_admin)):
	config = get_config()
	config["signup_locked"] = False
	save_config(config)
	return {"status": "unlocked"}

@app.get("/admin/list_users")
def admin_list_users(_: str = Depends(require_admin)):
	return list_users(include_admin=True)

# ✅ New public user list endpoint
@app.get("/users")
def public_user_list(_: str = Depends(get_current_user)):
	return list_users(include_admin=False)

@app.post("/admin/delete_user")
def delete_user_route(target: str = Form(...), admin: str = Depends(require_admin)):
	if target == admin:
		raise HTTPException(status_code=400, detail="Cannot delete yourself")
	if not user_exists(target):
		raise HTTPException(status_code=404, detail="User not found")
	delete_user(target)
	return {"status": "deleted"}

@app.get("/feed")
def get_feed(token: str = Depends(oauth2_scheme)):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT videos.username, videos.filename, videos.caption, videos.timestamp, users.avatar
		FROM videos
		JOIN users ON videos.username = users.username
		ORDER BY videos.timestamp DESC
	""")
	feed = [
		{
			"username": row[0],
			"filename": row[1],
			"caption": row[2],
			"timestamp": row[3],
			"avatar": row[4],
		}
		for row in c.fetchall()
	]
	conn.close()
	return feed


if __name__ == "__main__":
	import uvicorn
	uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
