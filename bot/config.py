from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    bot_token: str = ""
    admin_ids: list[int] = []
    database_url: str = f"sqlite+aiosqlite:///{(ROOT / 'data' / 'bot.db').as_posix()}"
    timezone: str = "Asia/Almaty"
    business_file: Path = ROOT / "business.yaml"
    slot_step_minutes: int = 30
    booking_days_ahead: int = 14

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def business(self) -> dict:
        return yaml.safe_load(self.business_file.read_text(encoding="utf-8"))


settings = Settings()
