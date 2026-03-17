"""Application configuration — reads from environment variables / .env file."""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional


@dataclass
class Settings:
    # --- AI ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # --- Security ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "trade-api-super-secret-key-change-in-prod-2024")
    MASTER_API_KEY: str = os.getenv("MASTER_API_KEY", "trade-master-key-2024")

    # --- Search ---
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")   # optional - falls back to DuckDuckGo


settings = Settings()
