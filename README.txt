# Documentation: Petal Frame Server Cleanup & Modularization

## Structure
- `main.py`: Entry point that mounts static files and includes all route modules.
- `modules/`:
    - `auth.py`: Login, registration, password hashing, token generation.
    - `users.py`: Avatar upload, profile fetching.
    - `uploads.py`: Video uploads and `/feed`.
    - `rooms.py`: HTML profile editor and viewing.
    - `admin.py`: Admin tools like lock/unlock signup and delete users.
    - `config.py`: Constants like folder paths, database location, JWT keys.
    - `database.py`: DB initialization and helpers like user lookup, insert, etc.
    - `utils.py`: Helper functions like bleach sanitization rules.

## Cleanups & Improvements
- 🔄 **Modularized all code** into appropriate domains.
- 🧹 Removed all duplicated or unreachable code (e.g., `get_user()` logic).
- 📁 All paths, DB constants, and keys moved to `config.py`.
- ✅ **Case-insensitive username matching** added via helper function in `database.py`, used consistently in routes.
- 🖼️ Avatars always saved in lowercase for filename consistency.
- 🧼 `/room/{username}` and other endpoints internally resolve canonical casing (e.g., `Parker` vs `parker`) using DB lookup.

## Casing Fix
- The system now uses a helper `resolve_username_caseless(name)` that checks the DB and returns the actual cased version stored.
- This ensures that `/room/parker` or `/room/PARKER` will resolve to the same canonical username and load their room.