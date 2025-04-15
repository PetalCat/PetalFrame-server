from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.security import OAuth2PasswordBearer
import os, shutil
from uuid import uuid4
import sqlite3
from modules.config import UPLOAD_DIR, DB_PATH
from modules.database import track_upload, list_user_uploads
from modules.auth import decode_token
from modules.database import user_exists

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

@router.post("/upload")
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
