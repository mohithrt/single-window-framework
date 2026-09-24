from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class InspectionUpdateRequest(BaseModel):
    status: str | None = None
    checklist: list[dict] | None = Field(default=None, max_length=100)
    findings: str | None = Field(default=None, max_length=12000)
    remarks: str | None = Field(default=None, max_length=12000)
    recommendation: str | None = Field(default=None, max_length=12000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if value not in {"SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}:
            raise ValueError("Unsupported inspection status")
        return value


class JointInspectionCreate(BaseModel):
    application_id: int
    approval_ids: list[int] = Field(min_length=2, max_length=7)
    scheduled_at: datetime
    site: str = Field(min_length=3, max_length=500)
    instructions: str | None = Field(default=None, max_length=4000)
    checklist: list[dict] = Field(default_factory=list, max_length=100)
    officer_assignments: dict[int, int] = Field(default_factory=dict)

    @field_validator("scheduled_at")
    @classmethod
    def future_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Include a timezone offset when scheduling an inspection")
        if value.astimezone(UTC) <= datetime.now(UTC):
            raise ValueError("Inspection time must be in the future")
        return value

    @field_validator("approval_ids")
    @classmethod
    def unique_approvals(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("Each participating department must be selected once")
        return values

    @field_validator("site")
    @classmethod
    def trim_site(cls, value: str) -> str:
        return value.strip()


class JointInspectionUpdateRequest(InspectionUpdateRequest):
    site: str | None = Field(default=None, min_length=3, max_length=500)
    instructions: str | None = Field(default=None, max_length=4000)
