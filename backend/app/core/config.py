from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    SECRET_KEY: str
    PASSWORD_PEPPER: str

    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 7

    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173"]'
    UPLOAD_DIR: str = "app/static/uploads"
    MAX_UPLOAD_SIZE_MB: int = 5
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"

    DEBUG: bool = False

    def get_cors_origins(self) -> List[str]:
        return json.loads(self.BACKEND_CORS_ORIGINS)

    def get_allowed_extensions(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]


settings = Settings()
