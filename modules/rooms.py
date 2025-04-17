from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer
import os
from modules.utils import sanitize_html, format_html
from modules.database import resolve_username_caseless, user_exists
from modules.auth import decode_token
from modules.config import ROOMS_DIR

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username

def get_room_path(username):
	return os.path.join(ROOMS_DIR, f"{username}.html")

@router.get("/room/{username}")
def get_user_room(username: str, requester: str = Depends(get_current_user)):
	resolved = resolve_username_caseless(username)
	if not resolved:
		return HTMLResponse(content="<p>User not found.</p>", status_code=404)

	path = get_room_path(resolved)

	if not os.path.exists(path) and resolved.lower() == requester.lower():
		default_path = os.path.join(TEMPLATES_DIR, "default_profile.html")
		if os.path.exists(default_path):
			with open(default_path, "r", encoding="utf-8") as f:
				default_html = f.read()
			with open(path, "w", encoding="utf-8") as f:
				f.write(default_html.strip())

	if not os.path.exists(path):
		return HTMLResponse(content="<p>This user has no profile page yet.</p>", status_code=404)

	with open(path, "r", encoding="utf-8") as f:
		return HTMLResponse(content=f.read())

@router.post("/room/save")
def save_user_room(html: str = Form(...), username: str = Depends(get_current_user)):
	sanitized = sanitize_html(html)
	formatted = format_html(sanitized)
	with open(get_room_path(username), "w", encoding="utf-8") as f:
		f.write(formatted)
	return {"status": "saved"}
