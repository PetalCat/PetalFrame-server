from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import sqlite3
from modules.auth import decode_token, get_user
from modules.database import user_exists
from modules.config import DB_PATH

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

def is_admin(username: str) -> bool:
	user = get_user(username)
	return user.get("is_admin", 0) == 1

@router.post("/edit-date")
def edit_date(data: dict, username: str = Depends(get_current_user)):
	filename = data.get("filename")
	new_timestamp = data.get("new_timestamp")
	if not filename or not isinstance(new_timestamp, int):
		raise HTTPException(status_code=400, detail="Invalid input")

	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	# Check permission
	if not is_admin(username):
		c.execute("SELECT username FROM videos WHERE filename = ?", (filename,))
		row = c.fetchone()
		if not row or row[0] != username:
			conn.close()
			raise HTTPException(status_code=403, detail="Not authorized to edit this file")

	c.execute("UPDATE videos SET date_taken = ? WHERE filename = ?", (new_timestamp, filename))
	conn.commit()
	conn.close()

	return {"status": "ok", "filename": filename, "new_date_taken": new_timestamp}
