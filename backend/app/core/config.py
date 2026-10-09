from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List
import json
import os


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

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_SSL: bool = False
    # "smtp" preserva provedores existentes. Contas pessoais Outlook usam
    # Microsoft Graph com consentimento delegado, sem senha da caixa postal.
    MAIL_DELIVERY_PROVIDER: str = "smtp"
    MICROSOFT_GRAPH_CLIENT_ID: str = ""
    MICROSOFT_GRAPH_REFRESH_TOKEN: str = ""
    MICROSOFT_GRAPH_TENANT: str = "consumers"
    MICROSOFT_GRAPH_SENDER_EMAIL: str = ""
    CLIENT_INVITE_BASE_URL: str = ""
    CLIENT_INVITE_TTL_MINUTES: int = 30

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
    # Temporariamente desativado: mantém código e dados de assinatura intactos,
    # mas bloqueia criação, validação e aplicação de assinaturas eletrônicas.
    ELECTRONIC_SIGNATURES_ENABLED: bool = False
    # O schema multimercado pode ser publicado com segurança enquanto a Europa
    # permanece inacessível. Ative somente após importar e conferir preços/IVA.
    # Catálogo e preços europeus foram reconciliados antes do lançamento.
    # O status persistido em markets.is_enabled continua sendo a segunda trava.
    EUROPE_MARKET_ENABLED: bool = True
    # EU continua sendo o mercado comercial; a primeira liberação aceita
    # somente Portugal até que regras fiscais e documentais de outro país
    # sejam aprovadas explicitamente.
    EU_LAUNCH_COUNTRY: str = "PT"

    BACKEND_CORS_ORIGINS: str = '["http://localhost:5173"]'
    # Deployments de produção/preview do projeto Ilya na conta Vercel indicada.
    # Mantém escopo restrito ao projeto; não equivale a liberar *.vercel.app.
    BACKEND_CORS_ORIGIN_REGEX: str = (
        r"^https://(?:ilya-rust|ilya-[a-z0-9-]+-kaioassis225s-projects)\.vercel\.app$"
    )
    UPLOAD_DIR: str = "app/static/uploads"
    MAX_UPLOAD_SIZE_MB: int = 5
    MAX_REQUEST_BODY_MB: int = 15
    CSV_IMPORT_STATEMENT_TIMEOUT_MS: int = 300_000
    ALLOWED_EXTENSIONS: str = "jpg,jpeg,png,webp"
    MAX_IMAGE_PIXELS: int = 25_000_000
    MAX_IMAGE_DIMENSION: int = 2560
    MEDIA_URL_TTL_SECONDS: int = 900
    # Chave independente da JWT. Quando vazia em desenvolvimento/testes, o
    # código deriva material separado de SECRET_KEY. Uma chave explícita permite
    # rotação independente da JWT; a anterior evita quebrar URLs emitidas no TTL.
    MEDIA_SIGNING_KEY: str = ""
    MEDIA_SIGNING_KEY_PREVIOUS: str = ""
    REQUIRE_PERSISTENT_MEDIA_STORAGE: bool = False

    # Armazenamento S3 compatível. Quando vazio, mantém o filesystem local.
    OBJECT_STORAGE_ENDPOINT: str = ""
    OBJECT_STORAGE_ACCESS_KEY_ID: str = ""
    OBJECT_STORAGE_SECRET_ACCESS_KEY: str = ""
    OBJECT_STORAGE_BUCKET: str = ""
    OBJECT_STORAGE_REGION: str = "auto"
    OBJECT_STORAGE_ADDRESSING_STYLE: str = "virtual"

    # Bucket próprio do mercado europeu. Fotos de produto e opcional EU vivem
    # nele, separadas do catálogo brasileiro: trocar ou apagar a foto de um
    # mercado nunca alcança o arquivo do outro, e extrair um mercado (Bloco 09)
    # leva os arquivos junto. Vazio = upload EU recusado quando o bucket
    # principal é de objetos, para não misturar os dois silenciosamente.
    OBJECT_STORAGE_EU_ENDPOINT: str = ""
    OBJECT_STORAGE_EU_ACCESS_KEY_ID: str = ""
    OBJECT_STORAGE_EU_SECRET_ACCESS_KEY: str = ""
    OBJECT_STORAGE_EU_BUCKET: str = ""
    OBJECT_STORAGE_EU_REGION: str = "auto"
    # Vazio herda o estilo do bucket principal: na Railway os dois são iguais.
    OBJECT_STORAGE_EU_ADDRESSING_STYLE: str = ""

    RATE_LIMIT_STORAGE_URI: str = "memory://"
    RATE_LIMIT_DEFAULT: str = "200/minute"
    # Login é anônimo, então esta cota externa é por IP. Numa feira/showroom a
    # equipe inteira sai pelo mesmo NAT, por isso o teto permite erros humanos.
    # A contenção dirigida fica no banco por fingerprint de origem+identificador:
    # uma rede atacante não bloqueia a identidade nas demais redes.
    RATE_LIMIT_LOGIN: str = "40/15minute"
    # Refresh é limitado por sessão (hash do cookie), não por IP — assim uma
    # sessão em loop é contida sem derrubar os colegas atrás do mesmo NAT.
    RATE_LIMIT_REFRESH: str = "10/minute"
    RATE_LIMIT_REDIS_TIMEOUT_SECONDS: float = 2.0
    LOGIN_FAILURE_WINDOW_MINUTES: int = 15
    LOGIN_DIRECTED_ALERT_THRESHOLD: int = 20
    LOGIN_ATTEMPT_RETENTION_DAYS: int = 7
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
    WEBHOOK_RETRY_AFTER_MAX_SECONDS: int = 86_400
    WEBHOOK_RESPONSE_BODY_MAX_BYTES: int = 4_096

    # Moloni: os segredos OAuth e a chave Fernet ficam exclusivamente no
    # ambiente. A conexão, empresa e mapeamento de IVA são persistidos no DB.
    MOLONI_ENABLED: bool = False
    MOLONI_CLIENT_ID: str = ""
    MOLONI_CLIENT_SECRET: str = ""
    MOLONI_REDIRECT_URI: str = ""
    MOLONI_TOKEN_ENCRYPTION_KEY: str = ""
    MOLONI_API_BASE_URL: str = "https://api.moloni.pt/v1"
    MOLONI_TIMEOUT_SECONDS: float = 15.0
    MOLONI_MAX_ATTEMPTS: int = 7
    MOLONI_DOCUMENT_SET_ID: int = 0
    MOLONI_LANGUAGE_ID: int = 1
    MOLONI_MATURITY_DATE_ID: int = 0
    MOLONI_PAYMENT_METHOD_ID: int = 0
    MOLONI_PRODUCT_CATEGORY_ID: int = 0
    MOLONI_PRODUCT_UNIT_ID: int = 0
    MOLONI_SALESMAN_ID: int = 182219

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

    def _eu_object_storage_values(self) -> tuple[str, str, str, str]:
        return (
            self.OBJECT_STORAGE_EU_ENDPOINT,
            self.OBJECT_STORAGE_EU_ACCESS_KEY_ID,
            self.OBJECT_STORAGE_EU_SECRET_ACCESS_KEY,
            self.OBJECT_STORAGE_EU_BUCKET,
        )

    def eu_object_storage_configured(self) -> bool:
        return all(self._eu_object_storage_values())

    def eu_object_storage_partially_configured(self) -> bool:
        values = self._eu_object_storage_values()
        return any(values) and not all(values)

    def persistent_media_storage_required(self) -> bool:
        """Produção Railway nunca pode cair silenciosamente no disco efêmero."""
        if self.DEBUG:
            return False
        return self.REQUIRE_PERSISTENT_MEDIA_STORAGE or bool(
            os.environ.get("RAILWAY_ENVIRONMENT_NAME")
            or os.environ.get("RAILWAY_PROJECT_ID")
        )


settings = Settings()
