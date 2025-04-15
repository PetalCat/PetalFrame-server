import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
AVATAR_DIR = os.path.join(ROOT_DIR, "avatars")
ROOMS_DIR = os.path.join(ROOT_DIR, "user_rooms")
DB_PATH = os.path.join(ROOT_DIR, "app.db")
CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 36000

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(ROOMS_DIR, exist_ok=True)

def get_config():
	if not os.path.exists(CONFIG_PATH):
		default = {
			"signup_locked": False,
			"secret_key": os.urandom(32).hex()
		}
		with open(CONFIG_PATH, "w") as f:
			json.dump(default, f)
	return json.load(open(CONFIG_PATH))

def save_config(config):
	with open(CONFIG_PATH, "w") as f:
		json.dump(config, f)

config = get_config()
SECRET_KEY = config["secret_key"]
