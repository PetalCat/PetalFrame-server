from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
import os, shutil
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import FileResponse
from modules.database import get_user, update_avatar, user_exists, list_users
from modules.config import AVATAR_DIR
from modules.auth import decode_token
from modules.database import get_user
from modules.database import resolve_username_caseless 
from modules.rooms import get_room_path  # Or define it if you haven't
from bs4 import BeautifulSoup

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

@router.get("/me")
def get_me(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	user = get_user(username)
	if not user:
		raise HTTPException(status_code=401, detail="Invalid token")
	return {
		"username": user["username"],
		"avatar": user["avatar"],
		"is_admin": user["is_admin"],  # ✅ include this
	}


@router.post("/me/avatar")
async def upload_avatar(username: str = Depends(get_current_user), file: UploadFile = File(...)):
	if not file.content_type.startswith("image/"):
		raise HTTPException(status_code=400, detail="Only image files allowed")
	ext = os.path.splitext(file.filename)[-1]
	filename = f"{username.lower()}{ext}"
	save_path = os.path.join(AVATAR_DIR, filename)
	with open(save_path, "wb") as f:
		shutil.copyfileobj(file.file, f)
	update_avatar(username, filename)
	return {"avatar": filename}

@router.get("/avatar/{filename}")
def get_avatar(filename: str, token: str = Depends(oauth2_scheme)):
	file_path = os.path.join(AVATAR_DIR, filename or "default-pfp.svg")
	if os.path.exists(file_path):
		return FileResponse(file_path)
	fallback = os.path.join("src", "assets", "default-pfp.svg")
	if os.path.exists(fallback):
		return FileResponse(fallback, media_type="image/svg+xml")
	raise HTTPException(status_code=404, detail="Avatar not found")

@router.get("/users")
def public_user_list(_: str = Depends(get_current_user)):
	return list_users(include_admin=False)


@router.get("/users/{username}")
def get_user_public(username: str):
	resolved = resolve_username_caseless(username)
	if not resolved:
		raise HTTPException(status_code=404, detail="User not found")

	user = get_user(resolved)
	bio = ""

	# Try to extract bio from user's room HTML
	try:
		path = get_room_path(resolved)
		if os.path.exists(path):
			with open(path, "r", encoding="utf-8") as f:
				html = f.read()
				soup = BeautifulSoup(html, "html.parser")
				bio_tag = soup.find("pf-bio")
				if bio_tag:
					bio = bio_tag.get_text(strip=True)
	except Exception as e:
		print(f"[WARN] Failed to parse bio for {resolved}: {e}")

	return {
		"username": user["username"],
		"avatar": user["avatar"],
		"bio": bio
	}
