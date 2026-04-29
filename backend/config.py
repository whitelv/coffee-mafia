from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "coffeedb"
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    esp_weight_stable_stddev: float = 1.0
    esp_weight_tolerance_percent: float = 5.0


settings = Settings()
