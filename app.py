"""
app.py — Render entry point for Crypto Sniper V2
Re-exports the FastAPI app from api.py.
Render start command: uvicorn app:app --host 0.0.0.0 --port $PORT
"""
from api import app  # noqa: F401 — Render looks for app:app

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
