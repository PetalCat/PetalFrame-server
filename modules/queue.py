import os, shutil, sqlite3, time, traceback
from datetime import datetime
from modules.uploads import convert_to_mp4, generate_preview, insert_into_album
from modules.database import track_upload
from modules.auth import decode_token
from modules.config import UPLOAD_DIR, QUEUE_DB_PATH

POLL_INTERVAL = 5  # seconds

def convert_and_track(username: str, tmp_path: str, final_name: str, caption: str, album_id: str = ""):
	output_path = os.path.join(UPLOAD_DIR, final_name)
	preview_name = f"preview_{final_name}"
	preview_path = os.path.join(UPLOAD_DIR, preview_name)
	try:
		convert_to_mp4(tmp_path, output_path)
		generate_preview(output_path, preview_path, is_video=True)
		track_upload(username, final_name, caption)
		insert_into_album(album_id, final_name)
	except Exception as e:
		print(f"[FFMPEG ERROR] {final_name}: {e}")
	finally:
		os.unlink(tmp_path)

def process_next():
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()

	c.execute("""
		SELECT id, username, original_path, final_name, caption, is_video, retry_count, album_id
		FROM upload_queue
		WHERE status = 'pending'
		ORDER BY created_at ASC
		LIMIT 1
	""")
	row = c.fetchone()

	if not row:
		conn.close()
		time.sleep(1)
		return False

	id, username, path, final_name, caption, is_video, retry_count, album_id = row

	c.execute("UPDATE upload_queue SET status = 'processing' WHERE id = ?", (id,))
	conn.commit()
	conn.close()

	try:
		convert_and_track(username, path, final_name, caption, album_id)
		conn = sqlite3.connect(QUEUE_DB_PATH)
		c = conn.cursor()
		c.execute("DELETE FROM upload_queue WHERE id = ?", (id,))
		conn.commit()
		conn.close()
		print(f"[Queue] ✅ Processed {final_name}")
	except Exception as e:
		print(f"[Queue] ❌ Failed {final_name}: {e}")
		conn = sqlite3.connect(QUEUE_DB_PATH)
		c = conn.cursor()
		if retry_count >= 3:
			c.execute("UPDATE upload_queue SET status = 'failed' WHERE id = ?", (id,))
		else:
			c.execute("UPDATE upload_queue SET status = 'pending', retry_count = ? WHERE id = ?", (retry_count + 1, id))
		conn.commit()
		conn.close()

	return True


# FastAPI routes
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
router = APIRouter()

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username:
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

@router.get("/queue/status")
def queue_status(username: str = Depends(get_current_user)):
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT id, final_name, caption, status, retry_count, created_at
		FROM upload_queue
		WHERE username = ?
		ORDER BY created_at ASC
	""", (username,))
	rows = c.fetchall()
	conn.close()
	return [
		{
			"id": r[0],
			"filename": r[1],
			"caption": r[2],
			"status": r[3],
			"retry_count": r[4],
			"created_at": r[5],
		} for r in rows
	]

@router.post("/queue/cancel")
def cancel_upload(id: int = Form(...), username: str = Depends(get_current_user)):
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("SELECT username, status, original_path FROM upload_queue WHERE id = ?", (id,))
	row = c.fetchone()
	if not row or row[0] != username:
		conn.close()
		raise HTTPException(status_code=404, detail="Upload not found")
	if row[1] == "processing":
		conn.close()
		raise HTTPException(status_code=400, detail="Cannot cancel in-progress upload")
	c.execute("DELETE FROM upload_queue WHERE id = ?", (id,))
	conn.commit()
	conn.close()
	if os.path.exists(row[2]):
		os.remove(row[2])
	return {"status": "cancelled"}

@router.post("/queue/retry")
def retry_upload(id: int = Form(...), username: str = Depends(get_current_user)):
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("SELECT username, status FROM upload_queue WHERE id = ?", (id,))
	row = c.fetchone()
	if not row or row[0] != username:
		conn.close()
		raise HTTPException(status_code=404, detail="Upload not found")
	if row[1] != "failed":
		conn.close()
		raise HTTPException(status_code=400, detail="Only failed uploads can be retried")
	c.execute("UPDATE upload_queue SET status = 'pending', retry_count = 0 WHERE id = ?", (id,))
	conn.commit()
	conn.close()
	return {"status": "retried"}

@router.get("/queue/pending")
def queue_pending():
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("SELECT COUNT(*) FROM upload_queue WHERE status = 'pending'")
	count = c.fetchone()[0]
	conn.close()
	return {"pending": count}

@router.get("/queue/all")
def queue_all():
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT id, username, final_name, status, retry_count, created_at
		FROM upload_queue
		ORDER BY created_at ASC
	""")
	rows = c.fetchall()
	conn.close()
	return [
		{
			"id": r[0],
			"username": r[1],
			"filename": r[2],
			"status": r[3],
			"retry_count": r[4],
			"created_at": r[5],
		} for r in rows
	]

def run_loop():
	print("[Queue] Started processing loop")
	while True:
		if not process_next():
			time.sleep(POLL_INTERVAL)
