from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RoleCode(StrEnum):
    APPLICANT = "APPLICANT"
    OFFICER = "OFFICER"
    ADMIN = "ADMIN"


class IndustryType(StrEnum):
    IT_SOFTWARE = "IT / Software"
    MANUFACTURING = "Manufacturing"
    FOOD_PROCESSING = "Food Processing"
    TEXTILE = "Textile"
    CHEMICAL = "Chemical"
    PHARMACEUTICAL = "Pharmaceutical"
    AUTOMOBILE = "Automobile"
    ELECTRONICS = "Electronics"
    LOGISTICS = "Logistics"
    OTHER = "Other"


class ApplicationStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    DOCUMENT_CORRECTION = "DOCUMENT_CORRECTION"
    INSPECTION_REQUIRED = "INSPECTION_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class PollutionCategory(StrEnum):
    WHITE = "White"
    GREEN = "Green"
    ORANGE = "Orange"
    RED = "Red"
    NOT_SURE = "Not sure"


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("code IN ('APPLICANT', 'OFFICER', 'ADMIN')", name="ck_roles_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(160), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    registration_number: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="company")
    departments: Mapped[list["Department"]] = relationship(back_populates="company")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_departments_company_code"),
        Index("ix_departments_company_name", "company_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="departments")
    users: Mapped[list["User"]] = relationship(back_populates="department")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(password_hash) > 0", name="ck_users_password_hash_nonempty"),
        Index("ix_users_role_active", "role_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    role: Mapped[Role] = relationship(back_populates="users")
    company: Mapped[Company | None] = relationship(back_populates="users")
    department: Mapped[Department | None] = relationship(back_populates="users")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'IN_REVIEW', 'ACTION_REQUIRED', 'APPROVED', 'REJECTED')",
            name="ck_applications_status",
        ),
        CheckConstraint(
            "industry_type IS NULL OR industry_type IN ('IT / Software', 'Manufacturing', 'Food Processing', 'Textile', 'Chemical', 'Pharmaceutical', 'Automobile', 'Electronics', 'Logistics', 'Other')",
            name="ck_applications_industry_type",
        ),
        CheckConstraint(
            "pollution_category IS NULL OR pollution_category IN ('White', 'Green', 'Orange', 'Red', 'Not sure')",
            name="ck_applications_pollution_category",
        ),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_applications_progress"),
        Index("ix_applications_owner_status", "owner_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    applicant_name: Mapped[str | None] = mapped_column(String(160))
    applicant_email: Mapped[str | None] = mapped_column(String(254))
    applicant_phone: Mapped[str | None] = mapped_column(String(30))

    company_name: Mapped[str | None] = mapped_column(String(200))
    pan: Mapped[str | None] = mapped_column(String(10))
    gstin: Mapped[str | None] = mapped_column(String(15))
    cin: Mapped[str | None] = mapped_column(String(21))
    udyam_number: Mapped[str | None] = mapped_column(String(30))

    industry_type: Mapped[str | None] = mapped_column(String(40))
    other_industry_name: Mapped[str | None] = mapped_column(String(120))
    project_type: Mapped[str | None] = mapped_column(String(100))
    project_description: Mapped[str | None] = mapped_column(String(5000))
    investment_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    number_of_employees: Mapped[int | None] = mapped_column(Integer)
    built_up_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    power_requirement: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    water_requirement: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    project_location: Mapped[str | None] = mapped_column(String(500))
    land_details: Mapped[str | None] = mapped_column(String(3000))
    midc_area: Mapped[bool | None] = mapped_column(Boolean)
    midc_area_name: Mapped[str | None] = mapped_column(String(160))

    pollution_category: Mapped[str | None] = mapped_column(String(24))
    hazardous_materials: Mapped[bool | None] = mapped_column(Boolean)
    hazardous_materials_details: Mapped[str | None] = mapped_column(String(3000))
    factory_information: Mapped[str | None] = mapped_column(String(3000))
    fire_safety_information: Mapped[str | None] = mapped_column(String(3000))

    risk_tier: Mapped[str | None] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ApplicationStatus.DRAFT.value,
        server_default=ApplicationStatus.DRAFT.value, index=True,
    )
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expected_completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship()
    company: Mapped[Company | None] = relationship()
    current_department: Mapped[Department | None] = relationship(foreign_keys=[current_department_id])
    documents: Mapped[list["ApplicationDocument"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )
    approvals: Mapped[list["ApplicationApproval"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )
    workflow_events: Mapped[list["WorkflowAuditEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True
    )


class ApplicationDocument(Base):
    __tablename__ = "application_documents"
    __table_args__ = (
        Index("ix_application_documents_application", "application_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PROCESSING", server_default="PROCESSING")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_fields: Mapped[dict | None] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="documents")


class ApplicationValidationIssue(Base):
    __tablename__ = "application_validation_issues"
    __table_args__ = (
        Index("ix_validation_issues_application_status", "application_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("application_documents.id", ondelete="CASCADE"), nullable=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    detected_value: Mapped[str | None] = mapped_column(String(255))
    expected_value: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship()
    document: Mapped[ApplicationDocument | None] = relationship()


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_assessments_score"),
        CheckConstraint("risk_tier IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_risk_assessments_tier"),
        Index("ix_risk_assessments_application_created", "application_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    assessed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    assessment_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    rules_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="risk_assessments")
    assessed_by: Mapped[User] = relationship()


class ApplicationApproval(Base):
    __tablename__ = "application_approvals"
    __table_args__ = (
        UniqueConstraint("application_id", "department_code", name="uq_application_approval_department"),
        CheckConstraint(
            "status IN ('NOT_STARTED', 'PENDING', 'IN_REVIEW', 'DOCUMENT_CORRECTION', 'INSPECTION_REQUIRED', 'APPROVED', 'REJECTED', 'ESCALATED')",
            name="ck_application_approvals_status",
        ),
        Index("ix_application_approvals_application_status", "application_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    department_code: Mapped[str] = mapped_column(String(24), nullable=False)
    department_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ApprovalStatus.NOT_STARTED.value)
    depends_on: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decision_message: Mapped[str | None] = mapped_column(Text)
    assigned_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_duration_days: Mapped[int | None] = mapped_column(Integer)
    sla_expected_completion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="approvals")
    assigned_reviewer: Mapped[User | None] = relationship()
    audit_events: Mapped[list["WorkflowAuditEvent"]] = relationship(back_populates="approval")
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="approval", cascade="all, delete-orphan", passive_deletes=True
    )
    inspection_participations: Mapped[list["InspectionParticipant"]] = relationship(back_populates="approval")


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint("inspection_type IN ('SINGLE', 'JOINT')", name="ck_inspections_type"),
        CheckConstraint("status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_inspections_status"),
        Index("ix_inspections_scheduled_type", "scheduled_at", "inspection_type"),
        Index("ix_inspections_application_status", "application_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[int] = mapped_column(ForeignKey("application_approvals.id", ondelete="CASCADE"), nullable=False)
    inspection_type: Mapped[str] = mapped_column(String(12), nullable=False, default="SINGLE")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SCHEDULED", server_default="SCHEDULED")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    scheduled_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    joint_inspection_id: Mapped[int | None] = mapped_column(ForeignKey("joint_inspections.id", ondelete="SET NULL"), index=True)
    site: Mapped[str | None] = mapped_column(String(500))
    checklist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    findings: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    remarks: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    application: Mapped[Application] = relationship()
    approval: Mapped[ApplicationApproval] = relationship(back_populates="inspections")
    scheduled_by: Mapped[User] = relationship(foreign_keys=[scheduled_by_user_id])
    updated_by: Mapped[User | None] = relationship(foreign_keys=[updated_by_user_id])
    joint_inspection: Mapped["JointInspection | None"] = relationship(back_populates="department_inspections")


class JointInspection(Base):
    __tablename__ = "joint_inspections"
    __table_args__ = (
        CheckConstraint("status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_joint_inspections_status"),
        Index("ix_joint_inspections_application_date", "application_id", "scheduled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    site: Mapped[str] = mapped_column(String(500), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SCHEDULED", server_default="SCHEDULED")
    checklist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    findings: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    remarks: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    scheduled_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    application: Mapped[Application] = relationship()
    scheduled_by: Mapped[User] = relationship(foreign_keys=[scheduled_by_user_id])
    updated_by: Mapped[User | None] = relationship(foreign_keys=[updated_by_user_id])
    department_inspections: Mapped[list[Inspection]] = relationship(back_populates="joint_inspection")
    participants: Mapped[list["InspectionParticipant"]] = relationship(back_populates="joint_inspection", cascade="all, delete-orphan")


class InspectionParticipant(Base):
    __tablename__ = "inspection_participants"
    __table_args__ = (
        UniqueConstraint("joint_inspection_id", "approval_id", name="uq_inspection_participant_approval"),
        Index("ix_inspection_participants_officer", "officer_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    joint_inspection_id: Mapped[int] = mapped_column(ForeignKey("joint_inspections.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[int] = mapped_column(ForeignKey("application_approvals.id", ondelete="CASCADE"), nullable=False)
    officer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="INVITED", server_default="INVITED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    joint_inspection: Mapped[JointInspection] = relationship(back_populates="participants")
    approval: Mapped[ApplicationApproval] = relationship(back_populates="inspection_participations")
    officer: Mapped[User | None] = relationship()


class WorkflowAuditEvent(Base):
    __tablename__ = "workflow_audit_events"
    __table_args__ = (
        Index("ix_workflow_events_application_created", "application_id", "created_at"),
        Index("ix_workflow_events_approval", "approval_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("application_approvals.id", ondelete="SET NULL"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    department_code: Mapped[str | None] = mapped_column(String(24), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped[Application] = relationship(back_populates="workflow_events")
    approval: Mapped[ApplicationApproval | None] = relationship(back_populates="audit_events")
    actor: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
        Index("ix_notifications_application", "application_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    application: Mapped[Application | None] = relationship()
