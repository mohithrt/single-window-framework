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


settings = Settings()
