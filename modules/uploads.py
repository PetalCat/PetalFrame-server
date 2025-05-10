# -------------------- Imports --------------------
from typing import List
from fastapi import UploadFile, File, Form, HTTPException, Depends, APIRouter, BackgroundTasks, Query
from fastapi.security import OAuth2PasswordBearer
import os, shutil, subprocess, tempfile, sqlite3, re
from uuid import uuid4
from datetime import datetime
from collections import defaultdict
from PIL import Image
from PIL.ExifTags import TAGS
from modules.database import (
    resolve_username_caseless, track_upload, list_user_uploads, user_exists, add_date_taken_column
)
from modules.config import UPLOAD_DIR, DB_PATH, QUEUE_DB_PATH
from modules.auth import decode_token
import os
from datetime import datetime
from fastapi.responses import FileResponse



# -------------------- Auth --------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    username = decode_token(token)
    if not username or not user_exists(username):
        raise HTTPException(status_code=401, detail="Invalid token")
    return username

# -------------------- Utilities --------------------
def generate_preview(input_path: str, output_path: str, is_video: bool):
    if is_video:
        if not output_path.lower().endswith(".jpg"):
            output_path = os.path.splitext(output_path)[0] + ".jpg"
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", "00:00:00.5",
            "-i", input_path,
            "-vframes", "1",
            "-vf", "scale=320:-1",
            output_path
        ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "scale=320:-1",
            "-frames:v", "1",
            "-update", "1",
            output_path
        ], check=True)


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
    preview_name = f"preview_{final_name}"
    preview_path = os.path.join(UPLOAD_DIR, preview_name)
    try:
        convert_to_mp4(tmp_path, output_path)
        generate_preview(output_path, preview_path, is_video=True)
        track_upload(username, final_name, caption)
    except Exception as e:
        print(f"[FFMPEG ERROR] {final_name}: {e}")
    finally:
        os.unlink(tmp_path)

def determine_date_taken(path: str) -> int | None:
	ext = os.path.splitext(path)[-1].lower()

	# 1. Try EXIF / ffprobe
	if ext in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
		taken = extract_date_taken_image(path)
		if taken:
			print(f"[Date] ⏱ EXIF: {path} → {taken}")
			return taken
	elif ext in [".mp4", ".webm", ".mov", ".avi", ".mkv", ".3gp"]:
		taken = extract_date_taken_video(path)
		if taken:
			print(f"[Date] 🎞️ FFPROBE: {path} → {taken}")
			return taken

	# 2. Fallback to filename
	taken = parse_date_from_filename(os.path.basename(path))
	if taken:
		print(f"[Date] 📄 Filename: {path} → {taken}")
	else:
		print(f"[Date] ❌ No valid timestamp found: {path}")

	return taken

def extract_date_taken_image(path: str) -> int | None:
    try:
        image = Image.open(path)
        exif = image._getexif()
        if not exif:
            return None
        for tag, value in exif.items():
            tag_name = TAGS.get(tag)
            if tag_name == "DateTimeOriginal":
                return int(datetime.strptime(value, "%Y:%m:%d %H:%M:%S").timestamp())
    except Exception as e:
        print(f"[EXIF ERROR] {path}: {e}")
    return None

def extract_date_taken_video(path: str) -> int | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format_tags=creation_time",
                "-i", path,
            ],
            capture_output=True,
            text=True
        )
        import json
        tags = json.loads(result.stdout).get("format", {}).get("tags", {})
        if "creation_time" in tags:
            return int(datetime.strptime(tags["creation_time"], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
    except Exception as e:
        print(f"[FFPROBE ERROR] {path}: {e}")
    return None


def parse_date_from_filename(filename: str) -> int | None:
	name = os.path.splitext(os.path.basename(filename))[0]

	# List of (regex pattern, datetime format, label)
	patterns = [
		(r"(\d{8})[-_](\d{6})", "%Y%m%d%H%M%S", "Google Photos"),
		(r"(\d{4})-(\d{2})-(\d{2}) (\d{2})\.(\d{2})\.(\d{2})", "%Y%m%d%H%M%S", "iCloud"),
		(r"(\d{4})-(\d{2})-(\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})", "%Y%m%d%H%M%S", "Screenshot"),
		(r"(\d{14})", "%Y%m%d%H%M%S", "Long Embed"),
		(r"(\d{4})[-_](\d{2})[-_](\d{2})", "%Y%m%d", "Fallback Date"),
	]

	for regex, fmt, label in patterns:
		match = re.search(regex, name)
		if match:
			try:
				date_str = "".join(match.groups())
				timestamp = int(datetime.strptime(date_str, fmt).timestamp())
				print(f"[Date Filename] 🏷️ Matched '{label}' → {timestamp}")
				return timestamp
			except ValueError:
				continue

	return None



def insert_into_album(album_id: str, filename: str):
	if not album_id:
		return
	try:
		conn = sqlite3.connect(DB_PATH)
		c = conn.cursor()
		c.execute(
			"INSERT OR IGNORE INTO album_items (album_id, filename) VALUES (?, ?)",
			(album_id, filename)
		)
		conn.commit()
		conn.close()
	except Exception as e:
		print(f"[Album Add] Failed to add {filename} to album {album_id}: {e}")



def backfill_missing_previews():
	for filename in os.listdir(UPLOAD_DIR):
		if filename.startswith("preview_"):
			continue  # Already has preview

		full_path = os.path.join(UPLOAD_DIR, filename)
		if not os.path.isfile(full_path):
			continue

		preview_name = f"preview_{filename}"
		preview_path = os.path.join(UPLOAD_DIR, preview_name)

		if os.path.exists(preview_path):
			continue  # Already generated

		ext = os.path.splitext(filename)[-1].lower()
		is_video = ext in [".mp4", ".webm", ".mov", ".avi", ".mkv", ".3gp"]
		try:
			generate_preview(full_path, preview_path, is_video)
			print(f"[Backfill] Generated preview for {filename}")
		except Exception as e:
			print(f"[Backfill] Failed preview for {filename}: {e}")


# -------------------- Uploads --------------------
router = APIRouter()

def enqueue_upload(username: str, tmp_path: str, final_name: str, caption: str, is_video: bool, album_id: str = ""):
	conn = sqlite3.connect(QUEUE_DB_PATH)
	c = conn.cursor()
	c.execute("""
	INSERT INTO upload_queue (
		username, original_path, final_name, caption, is_video, created_at, album_id
	) VALUES (?, ?, ?, ?, ?, ?, ?)
	""", (username, tmp_path, final_name, caption, int(is_video), int(datetime.now().timestamp()), album_id))
	conn.commit()
	conn.close()


@router.post("/upload")
async def upload_media(
    background_tasks: BackgroundTasks,
    username: str = Depends(get_current_user),
    caption: str = Form(""),
    album_id: str = Form(""),
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
            enqueue_upload(username, tmp_path, final_name, caption.strip(), is_video=True, album_id=album_id)
        else:
            is_video = content_type.startswith("video/")
            shutil.move(tmp_path, final_path)

            preview_name = f"preview_{final_name}"
            preview_path = os.path.join(UPLOAD_DIR, preview_name)
            generate_preview(final_path, preview_path, is_video)

            taken = determine_date_taken(final_path)
            track_upload(username, final_name, caption.strip(), date_taken=taken)
            insert_into_album(album_id, final_name)


        uploaded += 1

    return {"uploaded": uploaded}

# -------------------- Edit --------------------
@router.post("/media/edit_dates")
def edit_dates(
    filenames: List[str] = Form(...),
    timestamp: int = Form(...),
    username: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for filename in filenames:
        c.execute(
            "UPDATE videos SET date_taken = ? WHERE filename = ?",
            (timestamp, filename)
        )
    conn.commit()
    conn.close()

    return {"status": "ok"}

@router.post("/media/delete")
def delete_media(
    filenames: List[str] = Form(...),
    username: str = Depends(get_current_user)
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    deleted = 0

    for filename in filenames:
        # Confirm user owns the file
        c.execute("SELECT username FROM videos WHERE filename = ?", (filename,))
        row = c.fetchone()
        if not row:
            continue
        if row[0] != username:
            continue

        # Delete DB entry
        c.execute("DELETE FROM videos WHERE filename = ?", (filename,))
        deleted += 1

        # Remove files
        for name in [filename, f"preview_{filename}"]:
            path = os.path.join(UPLOAD_DIR, name)
            if os.path.exists(path):
                os.remove(path)

    conn.commit()
    conn.close()
    return {"deleted": deleted}

# -------------------- Gallery --------------------
@router.get("/gallery")
def gallery_data(_: str = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT videos.username, videos.filename, videos.caption, videos.timestamp, videos.date_taken, users.avatar
        FROM videos
        JOIN users ON videos.username = users.username
    """)
    rows = c.fetchall()
    conn.close()

    grouped = defaultdict(list)
    for row in rows:
        try:
            taken = row[4] or row[3]
            dt = datetime.fromtimestamp(taken)
            month_label = dt.strftime("%B %Y")
            grouped[month_label].append({
                "username": row[0],
                "filename": row[1],
                "caption": row[2],
                "timestamp": row[3],
                "date_taken": row[4],
                "avatar": row[5],
            })
        except Exception as e:
            print("[Gallery Debug] Skipped invalid:", row, e)

    # Sort inside each group
    for month in grouped:
        grouped[month].sort(key=lambda x: x["date_taken"] or x["timestamp"], reverse=True)

    return grouped

@router.get("/gallery/user/{username}")
def get_user_gallery(username: str):
    real_user = resolve_username_caseless(username)
    if not real_user:
        raise HTTPException(status_code=404, detail="User not found")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT filename, caption, timestamp, date_taken
        FROM videos
        WHERE username = ?
    """, (real_user,))
    uploads = c.fetchall()
    conn.close()

    grouped = defaultdict(list)
    for filename, caption, timestamp, date_taken in uploads:
        sort_time = date_taken or timestamp
        month = datetime.utcfromtimestamp(sort_time).strftime("%B %Y")
        grouped[month].append({
            "filename": filename,
            "caption": caption,
            "timestamp": timestamp,
            "date_taken": date_taken,
        })

    return grouped

# -------------------- Feed / My Uploads --------------------
@router.get("/my_uploads")
def my_uploads(username: str = Depends(get_current_user)):
    return list_user_uploads(username)

@router.get("/feed")
def get_feed(
    username: str = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT videos.username, videos.filename, videos.caption, videos.timestamp, users.avatar
        FROM videos
        JOIN users ON videos.username = users.username
        ORDER BY videos.timestamp DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = c.fetchall()
    conn.close()

    return [
        {
            "username": row[0],
            "filename": row[1],
            "preview_filename": f"preview_{row[1]}",
            "caption": row[2],
            "timestamp": row[3],
            "avatar": row[4],
        }
        for row in rows
    ]

# -------------------- Date Backfill --------------------
def backfill_date_taken():
	from modules.database import add_date_taken_column
	add_date_taken_column()

	conn = sqlite3.connect(DB_PATH)
	c = conn.cursor()
	c.execute("SELECT id, filename FROM videos WHERE date_taken IS NULL")
	rows = c.fetchall()

	for video_id, filename in rows:
		path = os.path.join(UPLOAD_DIR, filename)
		if not os.path.exists(path):
			continue

		ext = os.path.splitext(filename)[-1].lower()
		taken = None

		# Try EXIF / ffprobe
		if ext in [".jpg", ".jpeg", ".png", ".webp", ".heic"]:
			taken = extract_date_taken_image(path)
			if taken:
				print(f"[Backfill] ⏱ EXIF: {filename} → {taken}")
		elif ext in [".mp4", ".webm", ".mov", ".avi", ".mkv", ".3gp"]:
			taken = extract_date_taken_video(path)
			if taken:
				print(f"[Backfill] 🎞️ FFPROBE: {filename} → {taken}")

		# Fallback to filename pattern
		if not taken:
			taken = parse_date_from_filename(filename)
			if taken:
				print(f"[Backfill] 📄 Filename: {filename} → {taken}")
			else:
				print(f"[Backfill] ❌ No date found: {filename}")

		# Save if valid
		if taken:
			c.execute("UPDATE videos SET date_taken=? WHERE id=?", (taken, video_id))

	conn.commit()
	conn.close()


@router.get("/media/{filename}")
def serve_media(
	filename: str,
	username: str = Depends(get_current_user)
):
	file_path = os.path.join(UPLOAD_DIR, filename)
	if not os.path.isfile(file_path):
		raise HTTPException(status_code=404, detail="Media not found")
	return FileResponse(file_path)
