from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.security import OAuth2PasswordBearer
from modules.database import (
	list_users, delete_user, user_exists
)
from modules.config import get_config, save_config
from modules.auth import decode_token, get_user

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def require_admin(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	user = get_user(username)
	if not user or not user["is_admin"]:
		raise HTTPException(status_code=403, detail="Admin only")
	return username

@router.get("/admin/signup_status")
def get_signup_status(_: str = Depends(require_admin)):
	return {"locked": get_config()["signup_locked"]}

@router.post("/admin/lock_signup")
def lock_signup(_: str = Depends(require_admin)):
	config = get_config()
	config["signup_locked"] = True
	save_config(config)
	return {"status": "locked"}

@router.post("/admin/unlock_signup")
def unlock_signup(_: str = Depends(require_admin)):
	config = get_config()
	config["signup_locked"] = False
	save_config(config)
	return {"status": "unlocked"}

@router.get("/admin/list_users")
def admin_list_users(_: str = Depends(require_admin)):
	return list_users(include_admin=True)

@router.post("/admin/delete_user")
def admin_delete_user(target: str = Form(...), admin: str = Depends(require_admin)):
	if target.lower() == admin.lower():
		raise HTTPException(status_code=400, detail="Cannot delete yourself")
	if not user_exists(target, case_insensitive=True):
		raise HTTPException(status_code=404, detail="User not found")
	delete_user(target)
	return {"status": "deleted"}
