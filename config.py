import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    MONGO_URI = os.getenv("MONGO_URI", "").strip()
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_REGION = os.getenv("S3_REGION", "us-east-005")
    S3_BUCKET_PRIMARY = os.getenv("S3_BUCKET_PRIMARY")
    S3_BUCKET_BACKUP = os.getenv("S3_BUCKET_BACKUP")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
    S3_PUBLIC_BASE_URL_PRIMARY = os.getenv("S3_PUBLIC_BASE_URL_PRIMARY")
    S3_PUBLIC_BASE_URL_BACKUP = os.getenv("S3_PUBLIC_BASE_URL_BACKUP")
    ALLOWED_EXTENSIONS = {
        "txt",
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "csv",
        "json",
        "docx",
        "xlsx",
    }
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024
