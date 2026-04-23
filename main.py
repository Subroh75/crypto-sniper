"""
main.py — Backwards compatibility entry point.
Render uses api.py directly now via render.yaml.
"""
from api import app  # noqa

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
