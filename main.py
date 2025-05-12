from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from modules.auth import router as auth_router
from modules.users import router as users_router
from modules.uploads import router as uploads_router
from modules.rooms import router as rooms_router
from modules.admin import router as admin_router
from modules.edit import router as edit_router
from modules.config import UPLOAD_DIR
from modules.database import init_db, init_upload_queue_db, upgrade_main_db, upgrade_queue_db, add_date_taken_column  # ✅ import
from modules.albums import router as albums_router
from modules.uploads import backfill_normalize_uploads
import threading
from modules.queue import run_loop  # ⬅️ Import this
from modules.queue import router as queue_router
import os


app = FastAPI()

# Initialize the database
init_db()
init_upload_queue_db()
upgrade_main_db()
upgrade_queue_db()

add_date_taken_column() 

app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"https://localhost",
        "http://localhost",
        "https://localhost/",
        "http://localhost/",
		"http://localhost:8000",
		"http://localhost:5173",
		"https://petalcat.dev",
        "https://frame.petalcat.dev",
		"https://base.petalcat.dev",
		"https://sframe.petalcat.dev",
		"https://*.petalcat.dev",
	],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)




# Serve uploaded files (videos)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Register routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(uploads_router)
app.include_router(rooms_router)
app.include_router(admin_router)
app.include_router(edit_router)
app.include_router(albums_router)
app.include_router(queue_router)

backfill_normalize_uploads()

# Start queue processor in background
if os.getenv("RUN_MAIN") == "true":
	threading.Thread(target=run_loop, daemon=True).start()


if __name__ == "__main__":
	import uvicorn
	uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
