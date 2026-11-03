from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).parent.parent / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/salon_ai"
    jwt_secret: str
    jwt_ttl_hours: int = 24 * 7
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    salon_timezone: str = "Asia/Ashgabat"
    salon_currency: str = "TMT"
    slot_minutes: int = 30
    chat_limit_per_hour: int = 40
    nail_limit_per_hour: int = 15

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.salon_timezone)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
