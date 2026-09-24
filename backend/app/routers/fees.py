"""Application fee ledger, scoped to the signed-in applicant."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import Application, ApplicationFee, RoleCode

router = APIRouter(prefix="/fees", tags=["application fees"], dependencies=[Depends(require_roles(RoleCode.APPLICANT))])
Database = Annotated[Session, Depends(get_db)]


class FeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int
    application_number: str | None
    company_name: str | None
    fee_code: str
    description: str
    amount: Decimal
    currency: str
    status: str
    due_date: datetime | None
    paid_at: datetime | None
    receipt_reference: str | None


class FeeList(BaseModel):
    items: list[FeeRead]
    total_due: Decimal
    total_paid: Decimal


@router.get("", response_model=FeeList)
def list_fees(user: CurrentUser, db: Database) -> FeeList:
    rows = db.scalars(
        select(ApplicationFee).join(Application).where(Application.owner_user_id == user.id)
        .options(joinedload(ApplicationFee.application))
        .order_by(ApplicationFee.created_at.desc(), ApplicationFee.id.desc())
    ).unique().all()
    items = [FeeRead(
        id=row.id, application_id=row.application_id,
        application_number=row.application.application_number,
        company_name=row.application.company_name, fee_code=row.fee_code,
        description=row.description, amount=row.amount, currency=row.currency,
        status=row.status, due_date=row.due_date, paid_at=row.paid_at,
        receipt_reference=row.receipt_reference,
    ) for row in rows]
    return FeeList(
        items=items,
        total_due=sum((row.amount for row in rows if row.status == "DUE"), Decimal("0.00")),
        total_paid=sum((row.amount for row in rows if row.status == "PAID"), Decimal("0.00")),
    )


@router.get("/{application_id}", response_model=list[FeeRead])
def application_fees(application_id: int, user: CurrentUser, db: Database) -> list[FeeRead]:
    owned = db.scalar(select(Application.id).where(Application.id == application_id, Application.owner_user_id == user.id))
    if owned is None:
        raise HTTPException(status_code=404, detail="Application not found")
    rows = db.scalars(select(ApplicationFee).where(ApplicationFee.application_id == application_id)
                      .options(joinedload(ApplicationFee.application)).order_by(ApplicationFee.id)).unique().all()
    return [FeeRead(
        id=row.id, application_id=row.application_id,
        application_number=row.application.application_number,
        company_name=row.application.company_name, fee_code=row.fee_code,
        description=row.description, amount=row.amount, currency=row.currency,
        status=row.status, due_date=row.due_date, paid_at=row.paid_at,
        receipt_reference=row.receipt_reference,
    ) for row in rows]
