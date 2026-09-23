from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class OfficerRemarkRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Remark cannot be blank")
        return value


class InspectionScheduleRequest(BaseModel):
    inspection_type: str = "SINGLE"
    scheduled_at: datetime
    location: str = Field(min_length=3, max_length=500)
    instructions: str | None = Field(default=None, max_length=4000)

    @field_validator("inspection_type")
    @classmethod
    def valid_inspection_type(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"SINGLE", "JOINT"}:
            raise ValueError("Inspection type must be SINGLE or JOINT")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def require_future_date(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Include a timezone offset when scheduling an inspection")
        if value.astimezone(UTC) <= datetime.now(UTC):
            raise ValueError("Inspection time must be in the future")
        return value

    @field_validator("location")
    @classmethod
    def trim_location(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Enter an inspection location")
        return value

    @field_validator("instructions")
    @classmethod
    def trim_instructions(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None
