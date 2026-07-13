from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    PASSWORD_PEPPER: str

    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 7
    REFRESH_TOKEN_AUDIT_RETENTION_DAYS: int = 30

    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173"]'
    UPLOAD_DIR: str = "app/static/uploads"
    MAX_UPLOAD_SIZE_MB: int = 5
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"

    DEBUG: bool = False
    APP_VERSION: str = "0.1.0"

    def get_cors_origins(self) -> List[str]:
        try:
            return json.loads(self.BACKEND_CORS_ORIGINS)
        except json.JSONDecodeError:
            # Fallback seguro caso o usuario coloque uma URL direta separada por virgulas em vez de JSON
            return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

    def get_allowed_extensions(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]


settings = Settings()
