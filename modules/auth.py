from fastapi import APIRouter, Form, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from jose import jwt, JWTError
import time
from modules.database import add_user, get_user, user_count, user_exists
from modules.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_SECONDS, get_config
from modules.config import save_config

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain, hashed):
	return pwd_context.verify(plain, hashed)

def hash_password(pw):
	return pwd_context.hash(pw)

def create_token(username: str):
	exp = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS
	return jwt.encode({"sub": username, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		return payload.get("sub")
	except JWTError:
		return None

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(token: str = Depends(oauth2_scheme)):
	username = decode_token(token)
	if not username or not user_exists(username):
		raise HTTPException(status_code=401, detail="Invalid token")
	return username


@router.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
	if user_exists(username, case_insensitive=True):
		raise HTTPException(status_code=400, detail="Username taken (case-insensitive)")
	if get_config()["signup_locked"] and user_count() > 0:
		raise HTTPException(status_code=403, detail="Signups are locked")
	is_admin = user_count() == 0
	add_user(username, hash_password(password), is_admin)
	return {"msg": "User created", "is_admin": is_admin}

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
	user = get_user(form.username)
	if not user or not verify_password(form.password, user["hashed"]):
		time.sleep(1)
		raise HTTPException(status_code=401, detail="Bad credentials")
	token = create_token(form.username)
	return {"access_token": token, "token_type": "bearer"}
