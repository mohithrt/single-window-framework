"""Create the fixed role reference rows without creating demo users or companies."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Role, RoleCode

ROLE_DESCRIPTIONS = {
    RoleCode.APPLICANT.value: "Industrial applicant",
    RoleCode.OFFICER.value: "Department review officer",
    RoleCode.ADMIN.value: "Government administrator",
}


def seed_roles() -> None:
    with SessionLocal.begin() as db:
        for code, description in ROLE_DESCRIPTIONS.items():
            role = db.scalar(select(Role).where(Role.code == code))
            if role is None:
                db.add(Role(code=code, description=description))
    print("MAHACLEAR-AI role records are ready.")


if __name__ == "__main__":
    seed_roles()
