import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Runtime configuration sourced from environment variables."""

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://mahaclear:change-this-local-password@localhost:5432/mahaclear",
    )
    secret_key: str = os.getenv(
        "SECRET_KEY", "local-development-only-change-before-deployment-8d30e95f"
    )
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    demo_password: str = os.getenv("DEMO_PASSWORD", "MahaClearDemo2026!")
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    workflow_rules_path: str = os.getenv("WORKFLOW_RULES_PATH", "")
    sla_rules_path: str = os.getenv("SLA_RULES_PATH", "")
    sla_check_interval_seconds: int = int(os.getenv("SLA_CHECK_INTERVAL_SECONDS", "300"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_base_url: str = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    environment: str = os.getenv("ENVIRONMENT", "development").strip().lower()
    frontend_origins: list[str] = [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    def validate_production(self) -> None:
        """Fail fast when production is missing secrets or durable storage config."""
        if self.environment != "production":
            return

        if (
            len(self.secret_key) < 32
            or "local-development-only" in self.secret_key
            or "replace-this-with-a-random-secret" in self.secret_key
        ):
            raise RuntimeError("Production requires a unique SECRET_KEY of at least 32 characters")
        if not self.database_url.startswith("postgresql+") or any(
            host in self.database_url for host in ("localhost", "127.0.0.1", "change-this-local-password")
        ):
            raise RuntimeError("Production requires an externally reachable DATABASE_URL")
        invalid_origin = any(
            "*" in origin
            or urlsplit(origin).scheme != "https"
            or not urlsplit(origin).netloc
            or bool(urlsplit(origin).path or urlsplit(origin).query or urlsplit(origin).fragment)
            for origin in self.frontend_origins
        )
        if not self.frontend_origins or invalid_origin:
            raise RuntimeError("Production FRONTEND_ORIGINS must list exact HTTPS frontend origins")
        upload_dir = os.getenv("UPLOAD_DIR", "").strip()
        if not upload_dir or not os.path.isabs(upload_dir):
            raise RuntimeError("Production requires an absolute UPLOAD_DIR on persistent storage")


settings = Settings()
