import atexit
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

_test_dir = TemporaryDirectory(prefix="mahaclear-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_dir.name) / 'auth-test.db'}"
os.environ["SECRET_KEY"] = "test-only-secret-key-at-least-32-characters"
os.environ["UPLOAD_DIR"] = str(Path(_test_dir.name) / "uploads")

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Role, RoleCode, User
from app.seed_demo_users import ROLE_DESCRIPTIONS

Base.metadata.create_all(engine)
with SessionLocal.begin() as db:
    roles = {}
    for code, description in ROLE_DESCRIPTIONS.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, description=description)
            db.add(role)
            db.flush()
        roles[RoleCode(code)] = role
    for email, name, role_code in (
        ("officer@example.com", "Test Officer", RoleCode.OFFICER),
        ("admin@example.com", "Test Administrator", RoleCode.ADMIN),
    ):
        if db.scalar(select(User.id).where(User.email == email)) is None:
            db.add(
                User(
                    email=email,
                    full_name=name,
                    password_hash=hash_password("TestPassphrase2026!"),
                    role=roles[role_code],
                )
            )

atexit.register(engine.dispose)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
