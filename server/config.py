# server/config.py
import os
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/echoverse")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
ACCESS_TOKEN_EXPIRES = int(os.getenv("ACCESS_TOKEN_EXPIRES", "3600"))
