from pydantic import BaseModel, ConfigDict, Field, field_validator


class RejectionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def require_nonblank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A rejection reason is required")
        return value


class CorrectionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def require_nonblank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A correction message is required")
        return value


class WorkflowActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    department_code: str
    department_name: str
    is_required: bool
    status: str
    depends_on: list[str]
    decision_message: str | None

