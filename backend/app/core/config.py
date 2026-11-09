"""Application configuration loaded from environment variables (prefix ``PS_``)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

_DEV_SECRET = "change-me-dev-only-secret-key-please-rotate-0000000000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PS_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "uat", "production"] = "development"
    app_name: str = "ParishSphere"
    log_level: str = "INFO"
    log_json: bool = False

    # --- secrets ---
    secret_key: SecretStr = SecretStr(_DEV_SECRET)
    # Fernet key used to encrypt tenant DB credentials stored in the master DB.
    secret_encryption_key: SecretStr | None = None

    # --- master database ---
    master_database_url: str = "mysql+pymysql://ps_admin:ps_admin@localhost:3306/ps_master?charset=utf8mb4"
    master_pool_size: int = 10

    # --- tenant databases ---
    tenant_db_driver: Literal["mysql", "sqlite"] = "mysql"
    tenant_db_host: str = "localhost"
    tenant_db_port: int = 3306
    tenant_db_admin_user: str = "ps_admin"
    tenant_db_admin_password: SecretStr = SecretStr("ps_admin")
    # When true every tenant DB is accessed with the admin credentials (dev/test only).
    tenant_db_shared_credentials: bool = True
    tenant_db_name_prefix: str = "ps_t_"
    sqlite_data_dir: Path = BACKEND_DIR / "data"
    tenant_engine_cache_size: int = 200
    tenant_pool_size: int = 5
    tenant_max_overflow: int = 5
    tenant_pool_recycle_seconds: int = 1800

    # --- tenant resolution ---
    base_domain: str = "parishsphere.localhost"
    reserved_subdomains: list[str] = Field(default_factory=lambda: ["www", "app", "api", "admin", "platform"])
    tenant_cache_ttl_seconds: int = 300

    # --- auth ---
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_hours: int = 12
    idle_timeout_minutes: int = 30
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # --- infrastructure ---
    redis_url: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    expose_docs: bool = True

    @property
    def is_production(self) -> bool:
        return self.env in ("production", "uat")

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        if self.is_production:
            if (
                self.secret_key.get_secret_value() == _DEV_SECRET
                or len(self.secret_key.get_secret_value()) < 32
            ):
                raise ValueError("PS_SECRET_KEY must be set to a strong value outside development")
            if self.secret_encryption_key is None:
                raise ValueError("PS_SECRET_ENCRYPTION_KEY is required outside development")
            if self.tenant_db_shared_credentials:
                raise ValueError("PS_TENANT_DB_SHARED_CREDENTIALS must be false outside development")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
