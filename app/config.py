"""从环境变量读配置。密钥只从这里来，不进数据库。"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str
    ark_api_key: str | None
    secret_key: str | None
    cookie_secure: bool
    raw_dir: Path
    kb_dir: Path


def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'geo.db'}"),
        ark_api_key=os.environ.get("ARK_API_KEY") or None,
        secret_key=os.environ.get("SECRET_KEY") or None,
        cookie_secure=os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes"),
        raw_dir=Path(os.environ.get("RAW_DIR", str(ROOT / "data" / "raw" / "daily"))),
        kb_dir=Path(os.environ.get("KB_DIR", str(ROOT / "data" / "kb"))),
    )
