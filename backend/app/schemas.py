from datetime import datetime

from pydantic import AliasPath, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import RoleCode


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    company_name: str | None = Field(default=None, min_length=2, max_length=200)

    @field_validator("full_name", "company_name")
    @classmethod
    def trim_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Must contain at least two non-space characters")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: RoleCode = Field(validation_alias=AliasPath("role", "code"))
    company_id: int | None
    department_id: int | None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
