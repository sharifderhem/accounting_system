"""Environment-driven settings. Nothing secret lives in source code."""

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: str = field(
        default_factory=lambda: os.environ.get("DATABASE_PATH", str(BASE_DIR / "data" / "ledger.db"))
    )
    frontend_dir: str = field(
        default_factory=lambda: os.environ.get("FRONTEND_DIR", str(BASE_DIR.parent / "frontend"))
    )
    # First owner account, created on startup only when no owner exists yet.
    owner_username: str = field(default_factory=lambda: os.environ.get("OWNER_USERNAME", ""))
    owner_password: str = field(default_factory=lambda: os.environ.get("OWNER_PASSWORD", ""))
    owner_name: str = field(default_factory=lambda: os.environ.get("OWNER_NAME", "طه عادل"))
    # Send the session cookie only over HTTPS. Turn off for local development.
    secure_cookies: bool = field(default_factory=lambda: _bool("SECURE_COOKIES", True))
    session_days: int = field(default_factory=lambda: int(os.environ.get("SESSION_DAYS", "30")))
    # Business timezone: "today" is the factory's day, not the server's.
    timezone: str = field(default_factory=lambda: os.environ.get("APP_TIMEZONE", "Asia/Aden"))
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))


settings = Settings()
