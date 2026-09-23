from datetime import datetime
from decimal import Decimal
import re

from pydantic import AliasPath, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import ApplicationStatus, IndustryType, PollutionCategory


class ApplicationDraftWrite(BaseModel):
    """Partial, permissive payload for an in-progress wizard draft."""

    model_config = ConfigDict(extra="forbid")

    applicant_name: str | None = Field(default=None, max_length=160)
    applicant_email: str | None = Field(default=None, max_length=254)
    applicant_phone: str | None = Field(default=None, max_length=30)
    company_name: str | None = Field(default=None, max_length=200)
    pan: str | None = Field(default=None, max_length=10)
    gstin: str | None = Field(default=None, max_length=15)
    cin: str | None = Field(default=None, max_length=21)
    udyam_number: str | None = Field(default=None, max_length=30)
    industry_type: IndustryType | None = None
    other_industry_name: str | None = Field(default=None, max_length=120)
    project_type: str | None = Field(default=None, max_length=100)
    project_description: str | None = Field(default=None, max_length=5000)
    investment_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    number_of_employees: int | None = Field(default=None, ge=0, le=2_000_000)
    built_up_area: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    power_requirement: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    water_requirement: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    project_location: str | None = Field(default=None, max_length=500)
    land_details: str | None = Field(default=None, max_length=3000)
    midc_area: bool | None = None
    midc_area_name: str | None = Field(default=None, max_length=160)
    pollution_category: PollutionCategory | None = None
    hazardous_materials: bool | None = None
    hazardous_materials_details: str | None = Field(default=None, max_length=3000)
    factory_information: str | None = Field(default=None, max_length=3000)
    fire_safety_information: str | None = Field(default=None, max_length=3000)


class ApplicationSubmission(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=160)
    applicant_email: EmailStr
    applicant_phone: str = Field(min_length=10, max_length=30)
    company_name: str = Field(min_length=2, max_length=200)
    pan: str = Field(pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]$", max_length=10)
    gstin: str | None = Field(default=None, max_length=15)
    cin: str | None = Field(default=None, max_length=21)
    udyam_number: str | None = Field(default=None, max_length=30)
    industry_type: IndustryType
    other_industry_name: str | None = Field(default=None, max_length=120)
    project_type: str = Field(min_length=2, max_length=100)
    project_description: str = Field(min_length=20, max_length=5000)
    investment_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    number_of_employees: int = Field(ge=0, le=2_000_000)
    built_up_area: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    power_requirement: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    water_requirement: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    project_location: str = Field(min_length=5, max_length=500)
    land_details: str = Field(min_length=5, max_length=3000)
    midc_area: bool
    midc_area_name: str | None = Field(default=None, max_length=160)
    pollution_category: PollutionCategory
    hazardous_materials: bool
    hazardous_materials_details: str | None = Field(default=None, max_length=3000)
    factory_information: str = Field(min_length=5, max_length=3000)
    fire_safety_information: str = Field(min_length=5, max_length=3000)

    @field_validator("applicant_name", "company_name", "project_type", "project_location", "land_details", "factory_information", "fire_safety_information")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter at least two non-space characters")
        return value

    @field_validator("applicant_phone")
    @classmethod
    def validate_phone_digits(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not 10 <= len(digits) <= 15:
            raise ValueError("Enter a phone number containing 10 to 15 digits")
        return value.strip()

    @field_validator("pan", mode="before")
    @classmethod
    def normalize_pan(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{15}", value):
            raise ValueError("GSTIN must contain 15 letters or digits")
        return value

    @field_validator("cin")
    @classmethod
    def validate_cin(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[0-9A-Z]{21}", value):
            raise ValueError("CIN must contain 21 letters or digits")
        return value

    @model_validator(mode="after")
    def validate_industry_details(self) -> "ApplicationSubmission":
        if self.industry_type == IndustryType.OTHER and not (self.other_industry_name or "").strip():
            raise ValueError("Specify the industry when Other is selected")
        if self.hazardous_materials and not (self.hazardous_materials_details or "").strip():
            raise ValueError("Describe the hazardous materials")
        if self.midc_area and not (self.midc_area_name or "").strip():
            raise ValueError("Enter the MIDC area name")
        return self


class ApplicationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_type: str
    file_name: str
    media_type: str
    size_bytes: int
    status: str
    processed_at: datetime | None
    uploaded_at: datetime


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_number: str
    company_id: int | None
    applicant_name: str | None
    applicant_email: str | None
    applicant_phone: str | None
    company_name: str | None
    pan: str | None
    gstin: str | None
    cin: str | None
    udyam_number: str | None
    industry_type: str | None
    other_industry_name: str | None
    project_type: str | None
    project_description: str | None
    investment_amount: Decimal | None
    number_of_employees: int | None
    built_up_area: Decimal | None
    power_requirement: Decimal | None
    water_requirement: Decimal | None
    project_location: str | None
    land_details: str | None
    midc_area: bool | None
    midc_area_name: str | None
    pollution_category: str | None
    hazardous_materials: bool | None
    hazardous_materials_details: str | None
    factory_information: str | None
    fire_safety_information: str | None
    risk_tier: str | None
    status: ApplicationStatus
    progress_percent: int
    expected_completion_at: datetime | None
    current_department_name: str | None = Field(
        default=None, validation_alias=AliasPath("current_department", "name")
    )
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    documents: list[ApplicationDocumentRead]


class ApplicationSummary(BaseModel):
    total_applications: int
    pending: int
    approved: int
    rejected: int
    action_required: int


class ApplicantApplicationsResponse(BaseModel):
    summary: ApplicationSummary
    applications: list[ApplicationRead]
