import os

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
    redis_enabled: bool = os.getenv("REDIS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    redis_cache_ttl_seconds: int = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "120"))
    notification_mode: str = os.getenv("NOTIFICATION_MODE", "mock").lower()
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    sms_webhook_url: str = os.getenv("SMS_WEBHOOK_URL", "")
    integration_mode: str = os.getenv("INTEGRATION_MODE", "mock").lower()
    integration_timeout_seconds: int = int(os.getenv("INTEGRATION_TIMEOUT_SECONDS", "12") or "12")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_base_url: str = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1/chat/completions")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")


settings = Settings()
