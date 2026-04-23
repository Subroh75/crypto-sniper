from api import app  # noqa
if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)))
