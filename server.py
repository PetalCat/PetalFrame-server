from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import JWTError, jwt
from uuid import uuid4
from typing import Optional
import os, shutil, time, sqlite3, json

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],  # Keep open for dev, tighten for prod
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
DB_PATH = "app.db"
CONFIG_PATH = "config.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
ACCESS_TOKEN_EXPIRE_SECONDS = 3600

def get_signup_locked():
	return get_config()["signup_locked"]

def set_signup_locked(state: bool):
	config = get_config()
	config["signup_locked"] = state
	save_config(config)

# --- DB init ---
def init_db():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		CREATE TABLE IF NOT EXISTS users (
			username TEXT PRIMARY KEY,
			password TEXT NOT NULL,
			is_admin INTEGER NOT NULL
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

# --- User DB ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_user(username):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT password, is_admin FROM users WHERE username=?", (username,))
	row = c.fetchone()
	conn.close()
	if row:
		return {"hashed": row[0], "is_admin": bool(row[1])}
	return None

def user_exists(username):
	return get_user(username) is not None

def add_user(username, password, is_admin):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", (username, password, int(is_admin)))
	conn.commit()
	conn.close()

def list_users():
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT username, is_admin FROM users")
	users = [{"username": row[0], "is_admin": bool(row[1])} for row in c.fetchall()]
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

# --- Upload tracking ---
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

# --- Auth helpers ---
def verify_password(plain, hashed):
	return pwd_context.verify(plain, hashed)

def hash_password(pw):
	return pwd_context.hash(pw)

def create_token(username: str):
	expire = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS
	return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": True})
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
	if get_signup_locked() and user_count() > 0:
		raise HTTPException(status_code=403, detail="Signups are locked")
	is_admin = user_count() == 0
	add_user(username, hash_password(password), is_admin)
	return {"msg": "User created", "is_admin": is_admin}

@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
	user = get_user(form.username)
	if not user or not verify_password(form.password, user["hashed"]):
		time.sleep(1.0)  # Slow down brute force attempts
		raise HTTPException(status_code=401, detail="Bad credentials")
	token = create_token(form.username)
	return {"access_token": token, "token_type": "bearer"}

@app.post("/upload")
async def upload_video(
	username: str = Depends(get_current_user),
	caption: str = Form(""),
	file: UploadFile = File(...)
):
	if not file.content_type.startswith("video/"):
		raise HTTPException(status_code=400, detail="Only video files allowed")

	video_id = str(uuid4())
	ext = os.path.splitext(file.filename)[-1]
	filename = f"{video_id}{ext}"
	save_path = os.path.join(UPLOAD_DIR, filename)

	with open(save_path, "wb") as out_file:
		shutil.copyfileobj(file.file, out_file)

	clean_caption = caption.strip()
	track_upload(username, filename, clean_caption)
	return JSONResponse({"id": video_id, "filename": filename})

@app.get("/my_uploads")
def my_uploads(username: str = Depends(get_current_user)):
	return list_user_uploads(username)

# --- Admin ---

@app.get("/admin/signup_status")
def get_signup_status(_: str = Depends(require_admin)):
	return {"locked": get_signup_locked()}

@app.post("/admin/lock_signup")
def lock_signups(_: str = Depends(require_admin)):
	set_signup_locked(True)
	return {"status": "locked"}

@app.post("/admin/unlock_signup")
def unlock_signups(_: str = Depends(require_admin)):
	set_signup_locked(False)
	return {"status": "unlocked"}

@app.get("/admin/list_users")
def list_users_route(_: str = Depends(require_admin)):
	return list_users()

@app.post("/admin/delete_user")
def delete_user_route(target: str = Form(...), admin: str = Depends(require_admin)):
	if target == admin:
		raise HTTPException(status_code=400, detail="Cannot delete yourself")
	if not user_exists(target):
		raise HTTPException(status_code=404, detail="User not found")
	delete_user(target)
	return {"status": "deleted"}

if __name__ == "__main__":
	import uvicorn
	uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
