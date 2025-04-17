from typing import List
from fastapi import UploadFile, File, Form, HTTPException, Depends, APIRouter, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
import os, shutil, subprocess, tempfile, sqlite3
from uuid import uuid4

from modules.config import UPLOAD_DIR, DB_PATH
from modules.database import track_upload, list_user_uploads, user_exists
from modules.auth import decode_token
from datetime import datetime
from collections import defaultdict


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

def convert_to_mp4(input_path: str, output_path: str):
	subprocess.run([
		"ffmpeg", "-y", "-i", input_path,
		"-c:v", "libx264", "-preset", "fast",
		"-crf", "23",
		"-c:a", "aac", "-b:a", "128k",
		output_path
	], check=True)

def convert_and_track(username: str, tmp_path: str, final_name: str, caption: str):
	output_path = os.path.join(UPLOAD_DIR, final_name)
	try:
		convert_to_mp4(tmp_path, output_path)
		track_upload(username, final_name, caption)
	except Exception as e:
		print(f"[FFMPEG ERROR] {final_name}: {e}")
	finally:
		os.unlink(tmp_path)

@router.post("/upload")
async def upload_media(
	background_tasks: BackgroundTasks,
	username: str = Depends(get_current_user),
	caption: str = Form(""),
	files: List[UploadFile] = File(...)
):
	uploaded = 0
	for file in files:
		content_type = file.content_type
		ext = os.path.splitext(file.filename)[-1].lower()

		if not (content_type.startswith("image/") or content_type.startswith("video/")):
			continue

		with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
			shutil.copyfileobj(file.file, tmp)
			tmp_path = tmp.name

		file_id = str(uuid4())
		is_convert = ext in [".mov", ".heic", ".heif", ".3gp", ".mkv"]
		final_ext = ".mp4" if is_convert else ext
		final_name = f"{file_id}{final_ext}"
		final_path = os.path.join(UPLOAD_DIR, final_name)

		if is_convert:
			background_tasks.add_task(convert_and_track, username, tmp_path, final_name, caption.strip())
		else:
			shutil.move(tmp_path, final_path)
			track_upload(username, final_name, caption.strip())

		uploaded += 1

	return {"uploaded": uploaded}

@router.get("/my_uploads")
def my_uploads(username: str = Depends(get_current_user)):
	return list_user_uploads(username)

@router.get("/feed")
def get_feed(_: str = Depends(get_current_user)):
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

from fastapi import Depends
from datetime import datetime
import sqlite3
from modules.config import DB_PATH
from modules.auth import decode_token
from modules.database import user_exists
from fastapi.security import OAuth2PasswordBearer
from fastapi import HTTPException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

@router.get("/gallery")
def gallery_data(_: str = Depends(get_current_user)):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT videos.username, videos.filename, videos.caption, videos.timestamp, users.avatar
		FROM videos
		JOIN users ON videos.username = users.username
		ORDER BY videos.timestamp DESC
	""")
	rows = c.fetchall()
	conn.close()

	print("[Gallery Debug] Raw rows:", rows)

	grouped = defaultdict(list)
	for row in rows:
		try:
			dt = datetime.fromtimestamp(row[3])  # ✅ Fix: fromtimestamp not fromisoformat
			month_label = dt.strftime("%B %Y")
			grouped[month_label].append({
				"username": row[0],
				"filename": row[1],
				"caption": row[2],
				"timestamp": row[3],
				"avatar": row[4],
			})
		except Exception as e:
			print("[Gallery Debug] Invalid timestamp row:", row, e)

	print("[Gallery Debug] Grouped:", dict(grouped))
	return grouped
