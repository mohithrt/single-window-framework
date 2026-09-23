from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.database import get_db
from app.dependencies import CurrentUser
from app.models import Company, Role, RoleCode, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Database) -> User:
    email = str(payload.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    applicant_role = db.scalar(select(Role).where(Role.code == RoleCode.APPLICANT.value))
    if applicant_role is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Role records are not initialized; run the demo seed command",
        )

    company = None
    if payload.company_name:
        company = Company(name=payload.company_name.strip())
        db.add(company)
        db.flush()

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=applicant_role,
        company=company,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            ) from exc
        raise
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Database) -> TokenResponse:
    email = str(payload.email).strip().lower()
    user = db.scalar(
        select(User)
        .options(joinedload(User.role))
        .where(User.email == email)
    )
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
