"""Recreate a consistent, named set of MAHACLEAR-AI demonstration records.

Usage from backend/: python -m app.seed_demo_data seed
                   python -m app.seed_demo_data reset

Reset only removes the script's reserved MCAI-YYYY-900001..900010 demo records.
It never drops tables or removes users.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path

import fitz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models import (
    AIChatMessage, AIChatSession, Application, ApplicationApproval, ApplicationDocument,
    ApplicationFee, ApplicationValidationIssue, Department, Inspection, InspectionParticipant,
    IntegrationTransaction, JointInspection, Notification, RiskAssessment, User,
    WorkflowAuditEvent,
)
from app.prevalidation import DOCUMENT_LABELS
from app.risk_service import RiskService
from app.sla_service import SlaService
from app.workflow_service import WorkflowService
from app.seed_demo_users import seed_demo_users

DOCS = (
    "PAN", "GST_CERTIFICATE", "INCORPORATION_CERTIFICATE", "UDYAM_CERTIFICATE",
    "LAND_OWNERSHIP_LEASE", "BUILDING_PLAN", "PROJECT_REPORT", "ENVIRONMENTAL_DOCUMENTS",
    "FIRE_SAFETY_DOCUMENTS", "FACTORY_DOCUMENTS", "IDENTITY_DOCUMENT",
)

SCENARIOS = [
    dict(company="Asterbyte Systems Pvt Ltd", industry="IT / Software", pollution="White", hazardous=False,
         investment=7800000, area=6800, employees=34, power=68, water=12, midc=True,
         location="Plot 14, Rajiv Gandhi Infotech Park, Hinjawadi Phase II, Pune",
         case="IT · Low risk", days=18, states={"MCA21": "APPROVED", "GSTN": "PENDING"}),
    dict(company="Sahyadri Precision Components Pvt Ltd", industry="Manufacturing", pollution="Orange", hazardous=False,
         investment=68000000, area=28400, employees=186, power=420, water=95, midc=True,
         location="Plot B-17, Chakan MIDC Phase II, Khed, Pune",
         case="Manufacturing · Medium risk", days=24,
         states={"MPCB": "IN_REVIEW", "DISH": "PENDING", "MCA21": "PENDING", "GSTN": "PENDING"}),
    dict(company="Vardhan Specialty Chemicals Ltd", industry="Chemical", pollution="Red", hazardous=True,
         investment=485000000, area=118000, employees=420, power=1880, water=820, midc=True,
         location="Plot C-42, Taloja MIDC, Panvel, Raigad",
         case="Chemical · High risk", days=31,
         states={"MPCB": "IN_REVIEW", "DISH": "PENDING", "MCA21": "PENDING", "GSTN": "PENDING"}),
    dict(company="BlueKite Food Innovations Pvt Ltd", industry="Food Processing", pollution="Orange", hazardous=False,
         investment=42000000, area=22000, employees=112, power=310, water=240, midc=True,
         location="Plot F-9, Baramati Agro Industrial Estate, Pune",
         case="Missing environmental document · Action required", days=15,
         states={"MPCB": "DOCUMENT_CORRECTION", "DISH": "PENDING", "MCA21": "PENDING", "GSTN": "PENDING"},
         omit=["ENVIRONMENTAL_DOCUMENTS"]),
    dict(company="Nivara BioPharma Manufacturing Pvt Ltd", industry="Pharmaceutical", pollution="Orange", hazardous=True,
         investment=164000000, area=56500, employees=286, power=760, water=415, midc=True,
         location="Plot D-28, Hinjawadi Phase III, Pune",
         case="Document correction requested", days=20,
         states={"MPCB": "APPROVED", "DISH": "DOCUMENT_CORRECTION", "FIRE_SERVICES": "PENDING", "MCA21": "PENDING", "GSTN": "PENDING"}),
    dict(company="Kaveri Surface Technologies Ltd", industry="Automobile", pollution="Orange", hazardous=False,
         investment=92000000, area=41200, employees=248, power=490, water=180, midc=True,
         location="Plot A-31, Ranjangaon MIDC, Shirur, Pune",
         case="MPCB · SLA breached", days=36,
         states={"MPCB": "ESCALATED", "DISH": "PENDING", "MCA21": "PENDING", "GSTN": "PENDING"}),
    dict(company="Aarunya Textile Circularity Pvt Ltd", industry="Textile", pollution="Orange", hazardous=False,
         investment=73500000, area=36000, employees=205, power=440, water=360, midc=True,
         location="Plot T-12, Ichalkaranji Textile Park, Kolhapur",
         case="Joint site inspection", days=14,
         states={"MPCB": "INSPECTION_REQUIRED", "DISH": "INSPECTION_REQUIRED", "MCA21": "PENDING", "GSTN": "PENDING"}),
    dict(company="Pravaah Grid Analytics Pvt Ltd", industry="IT / Software", pollution="White", hazardous=False,
         investment=14500000, area=9400, employees=58, power=92, water=18, midc=True,
         location="Building 6, Magarpatta City, Hadapsar, Pune",
         case="Approved · All clearances recorded", days=68, final="APPROVED"),
    dict(company="Morya Clean Mobility Assemblies Pvt Ltd", industry="Automobile", pollution="Green", hazardous=False,
         investment=115000000, area=47300, employees=315, power=680, water=130, midc=True,
         location="Plot E-6, Supa Parner Industrial Park, Ahilyanagar",
         case="Pending · Awaiting department review", days=3, states={}),
    dict(company="Sudarshan Industrial Coatings Ltd", industry="Chemical", pollution="Red", hazardous=True,
         investment=152000000, area=62500, employees=292, power=920, water=330, midc=True,
         location="Plot P-19, Pimpri-Chinchwad Industrial Estate, Pune",
         case="Rejected · Reason recorded", days=74,
         states={"MPCB": "REJECTED"}, final="REJECTED"),
]


def demo_numbers() -> list[str]:
    return [f"MCAI-DEMO-2026-{index:02d}" for index in range(1, 11)]


def reset_demo(db: Session) -> int:
    app_ids = list(db.scalars(select(Application.id).where(Application.application_number.in_(demo_numbers()))).all())
    if not app_ids:
        return 0
    approval_ids = list(db.scalars(select(ApplicationApproval.id).where(ApplicationApproval.application_id.in_(app_ids))).all())
    inspection_ids = list(db.scalars(select(Inspection.id).where(Inspection.application_id.in_(app_ids))).all())
    joint_ids = list(db.scalars(select(JointInspection.id).where(JointInspection.application_id.in_(app_ids))).all())
    session_ids = list(db.scalars(select(AIChatSession.id).where(AIChatSession.application_id.in_(app_ids))).all())
    for model, column, values in (
        (AIChatMessage, AIChatMessage.session_id, session_ids),
        (AIChatSession, AIChatSession.id, session_ids),
        (InspectionParticipant, InspectionParticipant.joint_inspection_id, joint_ids),
        (InspectionParticipant, InspectionParticipant.approval_id, approval_ids),
        (Inspection, Inspection.id, inspection_ids),
        (JointInspection, JointInspection.id, joint_ids),
        (ApplicationFee, ApplicationFee.application_id, app_ids),
        (ApplicationValidationIssue, ApplicationValidationIssue.application_id, app_ids),
        (ApplicationDocument, ApplicationDocument.application_id, app_ids),
        (RiskAssessment, RiskAssessment.application_id, app_ids),
        (WorkflowAuditEvent, WorkflowAuditEvent.application_id, app_ids),
        (ApplicationApproval, ApplicationApproval.application_id, app_ids),
        (Notification, Notification.application_id, app_ids),
        (IntegrationTransaction, IntegrationTransaction.application_id, app_ids),
    ):
        if values:
            db.execute(delete(model).where(column.in_(values)))
    db.execute(delete(Application).where(Application.id.in_(app_ids)))
    return len(app_ids)


def make_pdf(storage_dir: Path, app_number: str, document_type: str, company: str) -> tuple[str, bytes, str]:
    key = f"demo/{app_number}-{document_type.lower()}.pdf"
    target = storage_dir / key
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((56, 62), "MAHACLEAR-AI · DEMONSTRATION DOCUMENT", fontsize=15)
    page.insert_text((56, 100), f"Company: {company}", fontsize=11)
    page.insert_text((56, 122), f"Record: {app_number}", fontsize=11)
    page.insert_text((56, 144), f"Document category: {DOCUMENT_LABELS[document_type]}", fontsize=11)
    page.insert_text((56, 176), "Clearly marked sample for prototype demonstration only.", fontsize=10)
    content = pdf.tobytes()
    pdf.close()
    target.write_bytes(content)
    return key, content, f"DEMO {DOCUMENT_LABELS[document_type]} for {company}; {app_number}. Prototype sample only."


def create_scenario(db: Session, applicant: User, officer: User, admin: User,
                    scenario: dict, index: int, now: datetime,
                    workflow: WorkflowService, sla: SlaService, risk_service: RiskService) -> Application:
    number, company = demo_numbers()[index], scenario["company"]
    submitted = now - timedelta(days=scenario["days"])
    missing = set(scenario.get("omit", []))
    state = scenario.get("final") or ("ACTION_REQUIRED" if index in (3, 4) else
             "IN_REVIEW" if index in (0, 1, 2, 5, 6) else "SUBMITTED")
    app = Application(
        application_number=number, owner_user_id=applicant.id, company_id=applicant.company_id,
        applicant_name=applicant.full_name, applicant_email=applicant.email,
        applicant_phone=f"+91 982{index + 100:03d} 245{index + 200:03d}",
        company_name=company, pan=f"{chr(65 + index)}BCDE{index + 1:04d}F",
        gstin=f"27{chr(65 + index)}BCDE{index + 1:04d}F1Z{index + 1}",
        cin=f"U{index + 1:05d}MH2022PLC{index + 7:06d}",
        udyam_number=f"UDYAM-MH-26-{index + 1:02d}-0000{index + 1}",
        industry_type=scenario["industry"], project_type="Greenfield / new unit",
        project_description=f"{scenario['industry']} facility at {scenario['location']}. Energy monitoring, documented controls, and phased commissioning are included in the project plan.",
        investment_amount=Decimal(str(scenario["investment"])), number_of_employees=scenario["employees"],
        built_up_area=Decimal(str(scenario["area"])), power_requirement=Decimal(str(scenario["power"])),
        water_requirement=Decimal(str(scenario["water"])), project_location=scenario["location"],
        land_details=f"Industrial plot in {scenario['location'].split(',')[0]}; MIDC lease and possession plan recorded.",
        midc_area=scenario["midc"], midc_area_name=scenario["location"].split(",")[0],
        pollution_category=scenario["pollution"], hazardous_materials=scenario["hazardous"],
        hazardous_materials_details="Closed-loop solvent recovery and listed chemical storage in bunded tanks." if scenario["hazardous"] else None,
        factory_information=f"{scenario['employees']} employees across two shifts; production and safety controls documented.",
        fire_safety_information="Addressable fire alarm, hydrants, portable extinguishers, marked exits, and quarterly drills.",
        risk_tier=None, status=state, progress_percent=100 if state in {"APPROVED", "REJECTED"} else 88,
        expected_completion_at=submitted + timedelta(days=35), created_at=submitted - timedelta(days=4),
        updated_at=now, submitted_at=submitted,
    )
    db.add(app)
    db.flush()

    storage_dir = Path(settings.upload_dir).expanduser().resolve()
    for document_type in DOCS:
        if document_type in missing:
            continue
        key, content, text = make_pdf(storage_dir, number, document_type, company)
        fields = {"pan": app.pan, "gstin": app.gstin, "cin": app.cin, "udyam_number": app.udyam_number}
        db.add(ApplicationDocument(
            application_id=app.id, document_type=document_type,
            file_name=f"{company.split()[0]}_{document_type.lower()}.pdf", storage_key=key,
            media_type="application/pdf", size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
            status="VALID", extracted_text=text, extracted_fields=fields,
            processed_at=submitted, uploaded_at=submitted - timedelta(days=3),
        ))
    db.flush()
    if missing:
        for doc_type in sorted(missing):
            db.add(ApplicationValidationIssue(
                application_id=app.id, document_type=doc_type, code="REQUIRED_MISSING", status="MISSING",
                message=f"{DOCUMENT_LABELS[doc_type]} is required before submission can proceed.",
                created_at=now - timedelta(days=2),
            ))
    else:
        db.add(ApplicationValidationIssue(
            application_id=app.id, document_type="PAN", code="IDENTITY_CHECK", status="VALID",
            message="PAN matches the submitted company information.", created_at=submitted,
        ))

    assessment = risk_service.assess(app)
    app.risk_tier = assessment["risk_tier"]
    db.add(RiskAssessment(
        application_id=app.id, assessed_by_user_id=admin.id, risk_score=assessment["risk_score"],
        risk_tier=assessment["risk_tier"], rules_version=assessment["rules_version"],
        assessment_data=assessment, input_snapshot=assessment["input_snapshot"],
        rules_snapshot=assessment["rules_snapshot"], created_at=submitted + timedelta(days=1),
    ))
    db.flush()

    approvals = workflow.initialize(db, app, applicant.id)
    db.flush()
    by_code = {row.department_code: row for row in approvals}
    states = scenario.get("states", {})
    if scenario.get("final") == "APPROVED":
        states = {row.department_code: "APPROVED" for row in approvals if row.is_required}
    for code, status in states.items():
        row = by_code[code]
        if not row.is_required:
            continue
        row.status = status
        row.assigned_reviewer_id = officer.id if status not in {"PENDING", "NOT_STARTED"} else None
        row.sla_duration_days = sla.duration(code)
        if status not in {"PENDING", "NOT_STARTED"}:
            row.sla_started_at = submitted + timedelta(days=2)
            row.sla_expected_completion = row.sla_started_at + timedelta(days=row.sla_duration_days)
        if status in {"APPROVED", "REJECTED"}:
            row.decided_at = submitted + timedelta(days=max(3, scenario["days"] - 2))
        if status == "ESCALATED":
            row.sla_started_at = now - timedelta(days=row.sla_duration_days + 2)
            row.sla_expected_completion = now - timedelta(days=2)
            row.escalated_at = now - timedelta(days=2)
            row.decision_message = f"{row.department_name} exceeded its {row.sla_duration_days}-day SLA; escalation recorded."
        elif status == "DOCUMENT_CORRECTION":
            row.decision_message = (
                "Please upload the environmental management plan and signed annexure."
                if index == 3 else "Please upload the signed, dimensioned building plan revision requested by the department."
            )
        elif status == "REJECTED":
            row.decision_message = "The process description does not include the required emissions-control design basis."
        elif status == "INSPECTION_REQUIRED":
            row.decision_message = "A site inspection is required before this department can complete review."
        row.updated_at = now - timedelta(days=max(0, scenario["days"] - 2))
    db.flush()

    for row in approvals:
        if not row.is_required:
            continue
        action = {
            "APPROVED": "APPROVED", "REJECTED": "REJECTED",
            "DOCUMENT_CORRECTION": "CORRECTION_REQUESTED", "INSPECTION_REQUIRED": "INSPECTION_REQUESTED",
            "ESCALATED": "SLA_BREACHED", "IN_REVIEW": "REVIEW_STARTED",
        }.get(row.status)
        if action:
            db.add(WorkflowAuditEvent(
                application_id=app.id, approval_id=row.id,
                actor_user_id=admin.id if row.status == "ESCALATED" else officer.id,
                action=action, department_code=row.department_code, from_status="PENDING", to_status=row.status,
                message=row.decision_message or f"{row.department_name} status is {row.status.replace('_', ' ').lower()}.",
                details={"system_actor": row.status == "ESCALATED", "demo_record": True}, created_at=row.updated_at,
            ))

    fee_status = "PAID" if scenario.get("final") == "APPROVED" else "DUE" if index in (3, 5, 8) else "ESTIMATED"
    db.add(ApplicationFee(
        application_id=app.id, fee_code="DEMO-APPLICATION-REVIEW",
        description="Prototype application review estimate (not a statutory government fee)",
        amount=Decimal("12500.00") if assessment["risk_tier"] == "HIGH" else Decimal("7500.00"),
        status=fee_status, due_date=now + timedelta(days=14) if fee_status == "DUE" else None,
        paid_at=submitted + timedelta(days=2) if fee_status == "PAID" else None,
        receipt_reference=f"DEMO-RCPT-{index + 1:04d}" if fee_status == "PAID" else None,
    ))

    if index == 6:
        selected = [by_code[c] for c in ("MPCB", "DISH") if c in by_code and by_code[c].is_required]
        joint = JointInspection(
            application_id=app.id, scheduled_at=now + timedelta(days=5), site=app.project_location,
            instructions="Joint site walk-through: verify effluent controls, machine guarding, and emergency access.",
            status="SCHEDULED", checklist=[{"item": "Effluent controls", "complete": False},
                                           {"item": "Machine guarding", "complete": False}],
            scheduled_by_user_id=officer.id,
        )
        db.add(joint)
        db.flush()
        for approval in selected:
            db.add(InspectionParticipant(joint_inspection_id=joint.id, approval_id=approval.id,
                                         officer_user_id=officer.id, status="INVITED"))
            db.add(Inspection(
                application_id=app.id, approval_id=approval.id, inspection_type="JOINT", status="SCHEDULED",
                scheduled_at=joint.scheduled_at, location=app.project_location, site=joint.site,
                instructions=joint.instructions, scheduled_by_user_id=officer.id,
                joint_inspection_id=joint.id, checklist=joint.checklist,
            ))
    elif index == 1:
        row = by_code["MPCB"]
        db.add(Inspection(
            application_id=app.id, approval_id=row.id, inspection_type="SINGLE", status="SCHEDULED",
            scheduled_at=now + timedelta(days=9), location=app.project_location, site=app.project_location,
            instructions="Verify consent-plan coordinates and wastewater collection points.",
            scheduled_by_user_id=officer.id,
        ))

    db.add(Notification(
        user_id=applicant.id, application_id=app.id, notification_type="DEMO_APPLICATION_UPDATE",
        message=f"{number} · {scenario['case']}. Check the application workspace for its current status.",
        is_read=index in (0, 1, 7, 8, 9), created_at=now - timedelta(days=max(0, scenario["days"] - 1)),
    ))
    db.flush()
    return app


def seed() -> int:
    seed_demo_users()
    with SessionLocal.begin() as db:
        reset_demo(db)
        applicant = db.scalar(select(User).where(User.email == "applicant@demo.com"))
        officer = db.scalar(select(User).where(User.email == "officer@demo.com"))
        admin = db.scalar(select(User).where(User.email == "admin@demo.com"))
        if not applicant or not officer or not admin:
            raise RuntimeError("Demo user seeding failed; demo applications were not created")
        workflow, sla, risk = WorkflowService(), SlaService(), RiskService()
        authority_departments = {}
        department_names = {row["code"]: row["name"] for row in workflow.departments}
        for code, name in department_names.items():
            department = db.scalar(select(Department).where(
                Department.company_id == applicant.company_id, Department.code == code,
            ))
            if department is None:
                department = Department(company_id=applicant.company_id, code=code, name=name)
                db.add(department)
                db.flush()
            authority_departments[code] = department
        now = datetime.now(UTC)
        for index, scenario in enumerate(SCENARIOS):
            app = create_scenario(db, applicant, officer, admin, scenario, index, now, workflow, sla, risk)
            live_states = {row.department_code: row.status for row in app.approvals if row.is_required}
            active_codes = [
                row.department_code for row in app.approvals
                if row.is_required and row.status in {"ESCALATED", "DOCUMENT_CORRECTION", "IN_REVIEW", "INSPECTION_REQUIRED"}
            ]
            if not active_codes and app.status not in {"APPROVED", "REJECTED"}:
                active_codes = [code for code, approval_status in live_states.items() if approval_status == "PENDING"]
            app.current_department_id = authority_departments[active_codes[0]].id if active_codes else None
            print(f"{app.application_number} | {app.company_name} | {app.status} | {app.risk_tier} | {scenario['case']}")
    print(f"Seeded {len(SCENARIOS)} application scenarios. Demo password: {settings.demo_password}")
    return len(SCENARIOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "reset"),
                        help="seed replaces the named demo fixtures; reset removes only those fixtures")
    command = parser.parse_args().command
    if command == "seed":
        seed()
    else:
        with SessionLocal.begin() as db:
            count = reset_demo(db)
        print(f"Removed {count} named demo applications; demo accounts and other records remain.")


if __name__ == "__main__":
    main()
