from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Company, Department, Role, RoleCode, User

ROLE_DESCRIPTIONS = {
    RoleCode.APPLICANT.value: "Industrial applicant",
    RoleCode.OFFICER.value: "Department review officer",
    RoleCode.ADMIN.value: "Government administrator",
}

DEMO_USERS = [
    ("applicant@demo.com", "Demo Applicant", RoleCode.APPLICANT),
    ("officer@demo.com", "Demo Officer", RoleCode.OFFICER),
    ("admin@demo.com", "Demo Administrator", RoleCode.ADMIN),
]


def seed_demo_users() -> None:
    with SessionLocal.begin() as db:
        roles: dict[RoleCode, Role] = {}
        for code, description in ROLE_DESCRIPTIONS.items():
            role = db.scalar(select(Role).where(Role.code == code))
            if role is None:
                role = Role(code=code, description=description)
                db.add(role)
                db.flush()
            roles[RoleCode(code)] = role

        company = db.scalar(select(Company).where(Company.name == "North-Star Demo Industries"))
        if company is None:
            company = Company(name="North-Star Demo Industries", registration_number="DEMO-NS-001")
            db.add(company)
            db.flush()

        department = db.scalar(
            select(Department).where(
                Department.company_id == company.id,
                Department.code == "DEMO-INDUSTRIES",
            )
        )
        if department is None:
            department = Department(
                company_id=company.id,
                name="Industrial Approvals Department",
                code="DEMO-INDUSTRIES",
            )
            db.add(department)
            db.flush()

        for email, full_name, role_code in DEMO_USERS:
            existing = db.scalar(select(User).where(User.email == email))
            if existing is not None:
                continue
            db.add(
                User(
                    email=email,
                    full_name=full_name,
                    password_hash=hash_password(settings.demo_password),
                    role=roles[role_code],
                    company=company if role_code in {RoleCode.APPLICANT, RoleCode.OFFICER} else None,
                    department=department if role_code == RoleCode.OFFICER else None,
                )
            )

    print("Demo roles, company, department, and users are ready.")
    print(f"Demo password: {settings.demo_password}")


if __name__ == "__main__":
    seed_demo_users()
