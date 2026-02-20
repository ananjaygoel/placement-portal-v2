from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    ApplicationStatusHistory,
    InterviewStatus,
    Placement,
    UserRole,
)


def parse_iso_date(value):
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def parse_salary(value):
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if parsed < 0:
        return None
    return parsed


def serialize_status_history(record: ApplicationStatusHistory):
    return {
        "id": record.id,
        "application_id": record.application_id,
        "previous_status": record.previous_status.value if record.previous_status else None,
        "new_status": record.new_status.value,
        "changed_by_user_id": record.changed_by_user_id,
        "changed_by_role": record.changed_by_role.value,
        "remarks": record.remarks,
        "changed_at": record.changed_at.isoformat(),
    }


def append_status_history(
    application: Application,
    previous_status: ApplicationStatus | None,
    new_status: ApplicationStatus,
    changed_by_role: UserRole,
    changed_by_user_id: int | None = None,
    remarks: str | None = None,
):
    entry = ApplicationStatusHistory(
        application_id=application.id,
        previous_status=previous_status,
        new_status=new_status,
        changed_by_user_id=changed_by_user_id,
        changed_by_role=changed_by_role,
        remarks=remarks,
    )
    db.session.add(entry)
    return entry


def update_application_status(
    application: Application,
    target_status: ApplicationStatus,
    changed_by_role: UserRole,
    changed_by_user_id: int | None = None,
    feedback: str | None = None,
    remarks: str | None = None,
    joining_date: date | None = None,
    offered_salary=None,
):
    if application.status == ApplicationStatus.PLACED and target_status != ApplicationStatus.PLACED:
        return "Placed applications cannot be moved to another status"

    previous_status = application.status
    if feedback is not None:
        cleaned_feedback = feedback.strip()
        application.company_feedback = cleaned_feedback or None

    if target_status in {
        ApplicationStatus.OFFER,
        ApplicationStatus.REJECTED,
        ApplicationStatus.PLACED,
    }:
        for interview in application.interviews:
            if interview.status == InterviewStatus.SCHEDULED:
                interview.status = InterviewStatus.CANCELLED

    if target_status == ApplicationStatus.PLACED:
        if joining_date is None:
            return "joining_date is required when setting status to placed"

        placement = application.placement
        if placement is None:
            placement = Placement(
                student_id=application.student_id,
                company_id=application.job_position.company_id,
                job_id=application.job_id,
                application_id=application.id,
                position_title=application.job_position.title,
                salary=offered_salary if offered_salary is not None else application.job_position.salary,
                joining_date=joining_date,
            )
            db.session.add(placement)
        else:
            placement.joining_date = joining_date
            if offered_salary is not None:
                placement.salary = offered_salary
    else:
        if application.placement and target_status != ApplicationStatus.PLACED:
            return "Application linked to placement can only remain in placed status"

    application.status = target_status

    if previous_status != target_status or remarks:
        append_status_history(
            application=application,
            previous_status=previous_status,
            new_status=target_status,
            changed_by_role=changed_by_role,
            changed_by_user_id=changed_by_user_id,
            remarks=remarks,
        )

    return None
