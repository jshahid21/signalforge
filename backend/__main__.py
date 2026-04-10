"""Entry point: python -m backend"""
import logging

import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("backend.api.app:app", host="0.0.0.0", port=8000, reload=True)
