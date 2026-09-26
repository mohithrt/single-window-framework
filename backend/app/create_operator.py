"""Provision an initial ADMIN or OFFICER account without exposing passwords in shell history."""

import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.database import SessionLocal
from app.models import Company, Department, Role, RoleCode, User


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument("--role", required=True, choices=(RoleCode.ADMIN.value, RoleCode.OFFICER.value))
    parser.add_argument("--company-name", help="Required for an OFFICER account")
    parser.add_argument("--department-code", help="Required for an OFFICER account, e.g. MPCB")
    parser.add_argument("--department-name", help="Required for an OFFICER account, e.g. MPCB")
    args = parser.parse_args()

    if args.role == RoleCode.OFFICER.value and not all(
        (args.company_name, args.department_code, args.department_name)
    ):
        parser.error("OFFICER requires --company-name, --department-code, and --department-name")

    password = getpass("Initial password (12+ characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        parser.error("Passwords must match and contain at least 12 characters")

    email = args.email.strip().lower()
    with SessionLocal.begin() as db:
        role = db.scalar(select(Role).where(Role.code == args.role))
        if role is None:
            parser.error("Role records are missing; run `python -m app.seed_roles` first")
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            parser.error("That email address is already registered")

        company = None
        department = None
        if args.role == RoleCode.OFFICER.value:
            company_name = args.company_name.strip()
            department_code = args.department_code.strip().upper()
            department_name = args.department_name.strip()
            company = db.scalar(select(Company).where(Company.name == company_name))
            if company is None:
                company = Company(name=company_name)
                db.add(company)
                db.flush()
            department = db.scalar(select(Department).where(
                Department.company_id == company.id,
                Department.code == department_code,
            ))
            if department is None:
                department = Department(
                    company_id=company.id,
                    code=department_code,
                    name=department_name,
                )
                db.add(department)

        db.add(User(
            email=email,
            full_name=args.full_name.strip(),
            password_hash=hash_password(password),
            role=role,
            company=company,
            department=department,
        ))
    print(f"Created {args.role} account for {email}.")


if __name__ == "__main__":
    main()
