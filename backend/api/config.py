"""
API Configuration module using pydantic-settings and environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


class Settings(BaseSettings):
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    class Config:
        extra = "ignore"


settings = Settings()
