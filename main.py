from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from modules.auth import router as auth_router
from modules.users import router as users_router
from modules.uploads import router as uploads_router
from modules.rooms import router as rooms_router
from modules.admin import router as admin_router
from modules.config import UPLOAD_DIR
from modules.database import init_db  # Import the init_db function

app = FastAPI()

# Initialize the database
init_db()

app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"https://localhost",                 # ✅ REQUIRED for Capacitor apps
		"http://localhost:8000",
		"http://localhost:5173",
		"https://petalcat.dev",
        "https://frame.petalcat.dev",
		"https://base.petalcat.dev",
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
