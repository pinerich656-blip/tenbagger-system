from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    line_notify_token: str | None = os.getenv("LINE_NOTIFY_TOKEN")
    twelve_data_api_key: str | None = os.getenv("TWELVE_DATA_API_KEY")

settings = Settings()
