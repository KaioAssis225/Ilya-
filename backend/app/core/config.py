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

    # Railway pode fornecer somente PGHOST/PGUSER/PGPASSWORD/PGDATABASE/PGPORT.
    # A validação de que uma das duas formas está completa fica centralizada
    # em app.db.url.resolve_async_database_url.
    DATABASE_URL: str = ""
    SECRET_KEY: str
    PASSWORD_PEPPER: str

    # Orçamento de conexões por processo. Em produção, o total máximo é:
    # replicas × workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW).
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_SECONDS: float = 10.0
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_COMMAND_TIMEOUT_SECONDS: float = 30.0
    DB_STATEMENT_TIMEOUT_MS: int = 30_000
    READINESS_TIMEOUT_SECONDS: float = 3.0

    ACCESS_TOKEN_TTL_MINUTES: int = 30
    REFRESH_TOKEN_TTL_DAYS: int = 7
    REFRESH_TOKEN_AUDIT_RETENTION_DAYS: int = 30

    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173"]'
    # Deployments de produção/preview do projeto Ilya na conta Vercel indicada.
    # Mantém escopo restrito ao projeto; não equivale a liberar *.vercel.app.
    BACKEND_CORS_ORIGIN_REGEX: str = (
        r"^https://(?:ilya-rust|ilya-[a-z0-9]+-kaioassis225s-projects)\.vercel\.app$"
    )
    UPLOAD_DIR: str = "app/static/uploads"
    MAX_UPLOAD_SIZE_MB: int = 5
    MAX_REQUEST_BODY_MB: int = 15
    CSV_IMPORT_STATEMENT_TIMEOUT_MS: int = 300_000
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"
    MAX_IMAGE_PIXELS: int = 25_000_000
    MAX_IMAGE_DIMENSION: int = 2560

    # Armazenamento S3 compatível. Quando vazio, mantém o filesystem local.
    OBJECT_STORAGE_ENDPOINT: str = ""
    OBJECT_STORAGE_ACCESS_KEY_ID: str = ""
    OBJECT_STORAGE_SECRET_ACCESS_KEY: str = ""
    OBJECT_STORAGE_BUCKET: str = ""
    OBJECT_STORAGE_REGION: str = "auto"
    OBJECT_STORAGE_ADDRESSING_STYLE: str = "virtual"

    RATE_LIMIT_STORAGE_URI: str = "memory://"
    RATE_LIMIT_DEFAULT: str = "200/minute"
    RATE_LIMIT_REDIS_TIMEOUT_SECONDS: float = 2.0
    GZIP_MINIMUM_SIZE: int = 1024
    GZIP_COMPRESS_LEVEL: int = 5
    SLOW_REQUEST_THRESHOLD_MS: float = 1000.0

    # Integração com o Ilya Estoque (webhooks assinados via Outbox).
    # TODAS com default de propósito: uma variável obrigatória aqui derrubaria
    # o boot da API se faltasse no ambiente. Sem WEBHOOK_ENABLED=true, nada é
    # enviado e a feature fica inerte.
    WEBHOOK_ENABLED: bool = False
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = ""
    WEBHOOK_TIMEOUT_SECONDS: float = 10.0
    WEBHOOK_MAX_ATTEMPTS: int = 7

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

    def object_storage_configured(self) -> bool:
        return all(
            (
                self.OBJECT_STORAGE_ENDPOINT,
                self.OBJECT_STORAGE_ACCESS_KEY_ID,
                self.OBJECT_STORAGE_SECRET_ACCESS_KEY,
                self.OBJECT_STORAGE_BUCKET,
            )
        )

    def object_storage_partially_configured(self) -> bool:
        values = (
            self.OBJECT_STORAGE_ENDPOINT,
            self.OBJECT_STORAGE_ACCESS_KEY_ID,
            self.OBJECT_STORAGE_SECRET_ACCESS_KEY,
            self.OBJECT_STORAGE_BUCKET,
        )
        return any(values) and not all(values)


settings = Settings()
