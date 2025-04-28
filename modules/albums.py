from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.security import OAuth2PasswordBearer
import sqlite3
from uuid import uuid4
from datetime import datetime
from modules.auth import decode_token
from modules.database import user_exists
from modules.config import DB_PATH

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username


@router.get("/albums")
def list_albums(username: str = Depends(get_current_user)):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT albums.id, albums.name, albums.description, albums.cover_filename,
		albums.creator_username,
		(SELECT COUNT(*) FROM album_items WHERE album_id = albums.id) as media_count
		FROM albums
	""")
	albums = c.fetchall()
	conn.close()

	return [
		{
			"id": row[0],
			"name": row[1],
			"description": row[2],
			"cover_filename": row[3],
			"creator": row[4],
			"media_count": row[5]
		}
		for row in albums
	]


@router.post("/albums")
def create_album(
	name: str = Form(...),
	description: str = Form(""),
	username: str = Depends(get_current_user)
):
	album_id = str(uuid4())
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		INSERT INTO albums (id, name, description, creator_username)
		VALUES (?, ?, ?, ?)
	""", (album_id, name.strip(), description.strip(), username))
	conn.commit()
	conn.close()

	return {"status": "created", "id": album_id}


@router.get("/album/{album_id}")
def get_album_info(album_id: str, username: str = Depends(get_current_user)):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT id, name, description, cover_filename, creator_username
		FROM albums
		WHERE id = ?
	""", (album_id,))
	row = c.fetchone()
	conn.close()

	if not row:
		raise HTTPException(status_code=404, detail="Album not found")

	return {
		"id": row[0],
		"name": row[1],
		"description": row[2],
		"cover_filename": row[3],
		"creator": row[4],
	}


@router.get("/album/{album_id}/media")
def get_album_media(album_id: str, username: str = Depends(get_current_user)):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("""
		SELECT videos.username, videos.filename, videos.caption, videos.timestamp, videos.date_taken, users.avatar
		FROM album_items
		JOIN videos ON album_items.filename = videos.filename
		JOIN users ON videos.username = users.username
		WHERE album_items.album_id = ?
	""", (album_id,))
	rows = c.fetchall()
	conn.close()

	grouped = {}
	for row in rows:
		try:
			taken = row[4] or row[3]
			dt = datetime.fromtimestamp(taken)
			month_label = dt.strftime("%B %Y")
			grouped.setdefault(month_label, []).append({
				"username": row[0],
				"filename": row[1],
				"caption": row[2],
				"timestamp": row[3],
				"date_taken": row[4],
				"avatar": row[5],
			})
		except Exception as e:
			print("[Album Gallery Debug] Skipped invalid:", row, e)

	for month in grouped:
		grouped[month].sort(key=lambda x: x["date_taken"] or x["timestamp"], reverse=True)

	return grouped


@router.post("/album/{album_id}/add")
def add_to_album(
	album_id: str,
	filenames: list[str] = Form(...),
	username: str = Depends(get_current_user)
):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	for filename in filenames:
		c.execute(
			"INSERT OR IGNORE INTO album_items (album_id, filename) VALUES (?, ?)",
			(album_id, filename)
		)

	conn.commit()
	conn.close()

	return {"status": "added", "count": len(filenames)}


@router.post("/album/{album_id}/remove")
def remove_from_album(
	album_id: str,
	filenames: list[str] = Form(...),
	username: str = Depends(get_current_user)
):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	for filename in filenames:
		c.execute("DELETE FROM album_items WHERE album_id=? AND filename=?", (album_id, filename))

	conn.commit()
	conn.close()

	return {"status": "removed", "count": len(filenames)}


@router.post("/album/{album_id}/delete")
def delete_album(
	album_id: str,
	confirm_name: str = Form(...),
	username: str = Depends(get_current_user)
):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT name, creator_username FROM albums WHERE id=?", (album_id,))
	row = c.fetchone()
	if not row:
		conn.close()
		raise HTTPException(status_code=404, detail="Album not found")

	name, creator = row
	if creator.lower() != username.lower():
		conn.close()
		raise HTTPException(status_code=403, detail="Only the creator can delete this album")

	if confirm_name != name:
		conn.close()
		raise HTTPException(status_code=400, detail="Album name mismatch")

	c.execute("DELETE FROM albums WHERE id=?", (album_id,))
	c.execute("DELETE FROM album_items WHERE album_id=?", (album_id,))
	conn.commit()
	conn.close()

	return {"status": "deleted"}
@router.post("/album/{album_id}/update")
def update_album(
	album_id: str,
	new_name: str = Form(None),
	new_description: str = Form(None),
	new_cover_filename: str = Form(None),
	username: str = Depends(get_current_user)
):
	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	c.execute("SELECT creator_username FROM albums WHERE id=?", (album_id,))
	row = c.fetchone()
	if not row:
		conn.close()
		raise HTTPException(status_code=404, detail="Album not found")

	creator = row[0]
	if creator.lower() != username.lower():
		conn.close()
		raise HTTPException(status_code=403, detail="Only the creator can edit the album")

	updates = []
	params = []

	if new_name is not None:
		updates.append("name = ?")
		params.append(new_name.strip())

	if new_description is not None:
		updates.append("description = ?")
		params.append(new_description.strip())

	if new_cover_filename is not None:
		updates.append("cover_filename = ?")
		params.append(new_cover_filename.strip())

	if not updates:
		conn.close()
		raise HTTPException(status_code=400, detail="No changes submitted")

	params.append(album_id)
	query = f"UPDATE albums SET {', '.join(updates)} WHERE id = ?"
	c.execute(query, tuple(params))
	conn.commit()
	conn.close()

	return {"status": "updated"}


@router.post("/album/{album_id}/cover")
def auto_pick_cover(
	album_id: str,
	username: str = Depends(get_current_user)
):
	require_album_owner(album_id, username)

	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()

	# Get current cover
	c.execute("SELECT cover_filename FROM albums WHERE id=?", (album_id,))
	row = c.fetchone()
	if not row:
		conn.close()
		raise HTTPException(status_code=404, detail="Album not found")

	current_cover = row[0]
	if current_cover:
		conn.close()
		return {"status": "skipped", "reason": "Cover already set"}

	# Find first media file in album
	c.execute("""
		SELECT filename FROM album_items
		WHERE album_id=?
		ORDER BY rowid ASC
		LIMIT 1
	""", (album_id,))
	row = c.fetchone()

	if not row:
		conn.close()
		return {"status": "skipped", "reason": "Album has no media"}

	first_filename = row[0]
	c.execute("UPDATE albums SET cover_filename=? WHERE id=?", (first_filename, album_id))
	conn.commit()
	conn.close()

	return {"status": "updated", "cover_filename": first_filename}
