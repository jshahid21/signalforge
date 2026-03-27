"""Entry point: python -m backend"""
import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000, reload=True)
