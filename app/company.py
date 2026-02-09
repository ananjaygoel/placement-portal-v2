from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, g, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Company,
    CompanyApprovalStatus,
    DriveStatus,
    Interview,
    InterviewStatus,
    JobPosition,
    Student,
    User,
    UserRole,
)
from app.security import token_required

company_bp = Blueprint("company", __name__)


def _parse_enum(value, enum_cls):
    if value is None:
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return None


def _parse_date(value):
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _parse_datetime(value):
    if value is None or value == "":
        return None
    raw_value = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_salary(value):
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if parsed < 0:
        return None
    return parsed


def _ensure_company_access():
    user = g.current_user
    company = user.company_profile
    if not company:
        return None, (jsonify({"error": "Company profile not found"}), 404)
    if company.approval_status != CompanyApprovalStatus.APPROVED:
        return None, (jsonify({"error": "Company is not approved by admin"}), 403)
    if not company.is_active or not user.is_active or user.is_blacklisted:
        return None, (jsonify({"error": "Company account is inactive or blacklisted"}), 403)
    return company, None


def _serialize_interview(interview: Interview):
    return {
        "id": interview.id,
        "application_id": interview.application_id,
        "company_id": interview.company_id,
        "scheduled_at": interview.scheduled_at.isoformat(),
        "interview_mode": interview.interview_mode,
        "meeting_link": interview.meeting_link,
        "location": interview.location,
        "notes": interview.notes,
        "status": interview.status.value,
        "created_at": interview.created_at.isoformat(),
        "updated_at": interview.updated_at.isoformat(),
    }


def _serialize_application(application: Application):
    student = application.student
    user = student.user if student else None
    interviews = sorted(
        application.interviews,
        key=lambda interview: interview.scheduled_at,
    )
    latest_interview = interviews[-1] if interviews else None
    return {
        "id": application.id,
        "job_id": application.job_id,
        "job_title": application.job_position.title if application.job_position else None,
        "student_id": application.student_id,
        "student_name": student.full_name if student else None,
        "student_branch": student.branch if student else None,
        "student_cgpa": student.cgpa if student else None,
        "student_contact": student.contact_number if student else None,
        "student_email": user.email if user else None,
        "status": application.status.value,
        "company_feedback": application.company_feedback,
        "applied_at": application.applied_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
        "latest_interview": _serialize_interview(latest_interview) if latest_interview else None,
        "interviews": [_serialize_interview(interview) for interview in interviews],
    }


def _serialize_job(job: JobPosition):
    applications = job.applications
    shortlisted_count = sum(
        1
        for application in applications
        if application.status in {ApplicationStatus.SHORTLISTED, ApplicationStatus.SELECTED}
    )
    selected_count = sum(
        1 for application in applications if application.status == ApplicationStatus.SELECTED
    )
    return {
        "id": job.id,
        "company_id": job.company_id,
        "title": job.title,
        "description": job.description,
        "salary": float(job.salary) if job.salary is not None else None,
        "skills_required": job.skills_required,
        "experience_required": job.experience_required,
        "benefits": job.benefits,
        "eligibility_branch": job.eligibility_branch,
        "minimum_cgpa": job.minimum_cgpa,
        "minimum_graduation_year": job.minimum_graduation_year,
        "application_deadline": job.application_deadline.isoformat(),
        "status": job.status.value,
        "applications_count": len(applications),
        "shortlisted_count": shortlisted_count,
        "selected_count": selected_count,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _job_for_company(company_id: int, job_id: int):
    return JobPosition.query.filter_by(id=job_id, company_id=company_id).first()


def _application_for_company(company_id: int, application_id: int):
    return (
        Application.query.join(JobPosition, Application.job_id == JobPosition.id)
        .filter(
            Application.id == application_id,
            JobPosition.company_id == company_id,
        )
        .first()
    )


@company_bp.get("/overview")
@token_required(UserRole.COMPANY)
def company_overview():
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    job_query = JobPosition.query.filter_by(company_id=company.id)
    application_query = Application.query.join(JobPosition).filter(
        JobPosition.company_id == company.id
    )

    jobs = job_query.order_by(JobPosition.created_at.desc()).all()
    shortlisted_candidates = (
        application_query.filter(
            Application.status.in_(
                [ApplicationStatus.SHORTLISTED, ApplicationStatus.SELECTED]
            )
        )
        .order_by(Application.updated_at.desc())
        .limit(15)
        .all()
    )

    return jsonify(
        {
            "role": "company",
            "company": {
                "id": company.id,
                "company_name": company.company_name,
                "industry": company.industry,
                "location": company.location,
                "approval_status": company.approval_status.value,
            },
            "summary": {
                "total_job_postings": len(jobs),
                "active_job_postings": sum(
                    1 for job in jobs if job.status == DriveStatus.APPROVED
                ),
                "closed_job_postings": sum(
                    1 for job in jobs if job.status == DriveStatus.CLOSED
                ),
                "pending_approval_job_postings": sum(
                    1 for job in jobs if job.status == DriveStatus.PENDING
                ),
                "received_applications": application_query.count(),
                "shortlisted_candidates": application_query.filter(
                    Application.status == ApplicationStatus.SHORTLISTED
                ).count(),
                "selected_candidates": application_query.filter(
                    Application.status == ApplicationStatus.SELECTED
                ).count(),
                "rejected_candidates": application_query.filter(
                    Application.status == ApplicationStatus.REJECTED
                ).count(),
            },
            "jobs": [_serialize_job(job) for job in jobs],
            "shortlisted_candidates": [
                _serialize_application(application) for application in shortlisted_candidates
            ],
        }
    )


@company_bp.post("/jobs")
@token_required(UserRole.COMPANY)
def create_job():
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    skills_required = (payload.get("skills_required") or "").strip()
    experience_required = (payload.get("experience_required") or "").strip()
    benefits = (payload.get("benefits") or "").strip()
    salary = _parse_salary(payload.get("salary"))

    if not title or not skills_required or not experience_required or not benefits:
        return jsonify(
            {
                "error": "title, skills_required, experience_required, and benefits are required"
            }
        ), 400
    if salary is None:
        return jsonify({"error": "Valid salary is required"}), 400

    deadline = _parse_date(payload.get("application_deadline"))
    if deadline is None:
        return jsonify({"error": "Valid application_deadline (YYYY-MM-DD) is required"}), 400
    if deadline < date.today():
        return jsonify({"error": "application_deadline cannot be in the past"}), 400

    job = JobPosition(
        company_id=company.id,
        title=title,
        description=(payload.get("description") or "").strip() or None,
        salary=salary,
        skills_required=skills_required,
        experience_required=experience_required,
        benefits=benefits,
        eligibility_branch=(payload.get("eligibility_branch") or "").strip() or None,
        minimum_cgpa=payload.get("minimum_cgpa"),
        minimum_graduation_year=payload.get("minimum_graduation_year"),
        application_deadline=deadline,
        status=DriveStatus.PENDING,
    )
    db.session.add(job)
    db.session.commit()

    return jsonify(
        {
            "message": "Job posting created and sent for admin approval",
            "job": _serialize_job(job),
        }
    ), 201


@company_bp.get("/jobs")
@token_required(UserRole.COMPANY)
def list_jobs():
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    query = JobPosition.query.filter_by(company_id=company.id)
    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            JobPosition.title.ilike(like_value),
            JobPosition.description.ilike(like_value),
            JobPosition.skills_required.ilike(like_value),
            JobPosition.experience_required.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(JobPosition.id == int(search_text))
        query = query.filter(or_(*search_filters))

    status_filter = _parse_enum(request.args.get("status"), DriveStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid job status"}), 400
    if status_filter:
        query = query.filter(JobPosition.status == status_filter)

    jobs = query.order_by(JobPosition.created_at.desc()).all()
    return jsonify({"jobs": [_serialize_job(job) for job in jobs]})


@company_bp.patch("/jobs/<int:job_id>/status")
@token_required(UserRole.COMPANY)
def update_job_status(job_id: int):
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    job = _job_for_company(company.id, job_id)
    if not job:
        return jsonify({"error": "Job posting not found"}), 404

    payload = request.get_json(silent=True) or {}
    target_status = _parse_enum(payload.get("status"), DriveStatus)
    if target_status not in {DriveStatus.APPROVED, DriveStatus.CLOSED}:
        return jsonify({"error": "Only approved(active) and closed statuses are allowed"}), 400

    if target_status == DriveStatus.CLOSED:
        if job.status != DriveStatus.APPROVED:
            return jsonify({"error": "Only active(approved) jobs can be closed"}), 400
        job.status = DriveStatus.CLOSED
    else:
        if job.status != DriveStatus.CLOSED:
            return jsonify({"error": "Only closed jobs can be reopened to active"}), 400
        job.status = DriveStatus.APPROVED

    db.session.commit()
    return jsonify({"message": "Job status updated", "job": _serialize_job(job)})


@company_bp.get("/jobs/<int:job_id>/applications")
@token_required(UserRole.COMPANY)
def list_job_applications(job_id: int):
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    job = _job_for_company(company.id, job_id)
    if not job:
        return jsonify({"error": "Job posting not found"}), 404

    query = Application.query.filter_by(job_id=job.id)
    status_filter = _parse_enum(request.args.get("status"), ApplicationStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid application status"}), 400
    if status_filter:
        query = query.filter(Application.status == status_filter)

    applications = query.order_by(Application.applied_at.desc()).all()
    return jsonify(
        {
            "job": _serialize_job(job),
            "applications": [_serialize_application(application) for application in applications],
        }
    )


@company_bp.get("/applications")
@token_required(UserRole.COMPANY)
def list_company_applications():
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    query = (
        Application.query.join(JobPosition, Application.job_id == JobPosition.id)
        .join(Student, Application.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .filter(JobPosition.company_id == company.id)
    )

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            Student.full_name.ilike(like_value),
            Student.contact_number.ilike(like_value),
            User.email.ilike(like_value),
            JobPosition.title.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(Application.id == int(search_text))
            search_filters.append(Application.student_id == int(search_text))
        query = query.filter(or_(*search_filters))

    status_filter = _parse_enum(request.args.get("status"), ApplicationStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid application status"}), 400
    if status_filter:
        query = query.filter(Application.status == status_filter)

    job_id = (request.args.get("job_id") or "").strip()
    if job_id:
        if not job_id.isdigit():
            return jsonify({"error": "job_id must be an integer"}), 400
        query = query.filter(Application.job_id == int(job_id))

    applications = query.order_by(Application.updated_at.desc()).all()
    return jsonify(
        {"applications": [_serialize_application(application) for application in applications]}
    )


@company_bp.patch("/applications/<int:application_id>/status")
@token_required(UserRole.COMPANY)
def update_application_status(application_id: int):
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    application = _application_for_company(company.id, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    payload = request.get_json(silent=True) or {}
    target_status = _parse_enum(payload.get("status"), ApplicationStatus)
    if target_status not in {
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.SELECTED,
        ApplicationStatus.REJECTED,
    }:
        return jsonify(
            {"error": "Status must be shortlisted, selected, or rejected"}
        ), 400

    feedback = (payload.get("feedback") or "").strip()
    if feedback:
        application.company_feedback = feedback

    application.status = target_status

    if target_status in {ApplicationStatus.SELECTED, ApplicationStatus.REJECTED}:
        for interview in application.interviews:
            if interview.status == InterviewStatus.SCHEDULED:
                interview.status = InterviewStatus.CANCELLED

    db.session.commit()
    return jsonify(
        {
            "message": "Application status updated",
            "application": _serialize_application(application),
        }
    )


@company_bp.post("/applications/<int:application_id>/interviews")
@token_required(UserRole.COMPANY)
def schedule_interview(application_id: int):
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    application = _application_for_company(company.id, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404
    if application.status != ApplicationStatus.SHORTLISTED:
        return jsonify({"error": "Only shortlisted applicants can be scheduled"}), 400

    payload = request.get_json(silent=True) or {}
    scheduled_at = _parse_datetime(payload.get("scheduled_at"))
    if scheduled_at is None:
        return jsonify({"error": "Valid scheduled_at datetime is required"}), 400
    if scheduled_at < datetime.utcnow():
        return jsonify({"error": "Interview datetime cannot be in the past"}), 400

    interview_mode = (payload.get("interview_mode") or "virtual").strip().lower()
    if interview_mode not in {"virtual", "in_person", "phone"}:
        return jsonify({"error": "interview_mode must be virtual, in_person, or phone"}), 400

    interview = Interview(
        application_id=application.id,
        company_id=company.id,
        scheduled_at=scheduled_at,
        interview_mode=interview_mode,
        meeting_link=(payload.get("meeting_link") or "").strip() or None,
        location=(payload.get("location") or "").strip() or None,
        notes=(payload.get("notes") or "").strip() or None,
        status=InterviewStatus.SCHEDULED,
    )
    db.session.add(interview)
    db.session.commit()

    return jsonify(
        {
            "message": "Interview scheduled successfully",
            "interview": _serialize_interview(interview),
            "application": _serialize_application(application),
        }
    ), 201


@company_bp.get("/interviews")
@token_required(UserRole.COMPANY)
def list_interviews():
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    query = (
        Interview.query.join(Application, Interview.application_id == Application.id)
        .join(JobPosition, Application.job_id == JobPosition.id)
        .filter(Interview.company_id == company.id, JobPosition.company_id == company.id)
    )

    status_filter = _parse_enum(request.args.get("status"), InterviewStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid interview status"}), 400
    if status_filter:
        query = query.filter(Interview.status == status_filter)

    job_id = (request.args.get("job_id") or "").strip()
    if job_id:
        if not job_id.isdigit():
            return jsonify({"error": "job_id must be an integer"}), 400
        query = query.filter(Application.job_id == int(job_id))

    interviews = query.order_by(Interview.scheduled_at.asc()).all()
    result = []
    for interview in interviews:
        application = interview.application
        result.append(
            {
                **_serialize_interview(interview),
                "job_id": application.job_id,
                "job_title": application.job_position.title
                if application.job_position
                else None,
                "student_name": application.student.full_name if application.student else None,
                "student_email": application.student.user.email
                if application.student and application.student.user
                else None,
                "application_status": application.status.value,
            }
        )

    return jsonify({"interviews": result})


@company_bp.patch("/interviews/<int:interview_id>/status")
@token_required(UserRole.COMPANY)
def update_interview_status(interview_id: int):
    company, error_response = _ensure_company_access()
    if error_response:
        return error_response

    interview = Interview.query.filter_by(id=interview_id, company_id=company.id).first()
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    payload = request.get_json(silent=True) or {}
    target_status = _parse_enum(payload.get("status"), InterviewStatus)
    if not target_status:
        return jsonify({"error": "Valid interview status is required"}), 400

    interview.status = target_status
    updated_notes = (payload.get("notes") or "").strip()
    if updated_notes:
        interview.notes = updated_notes

    db.session.commit()
    return jsonify(
        {
            "message": "Interview status updated",
            "interview": _serialize_interview(interview),
        }
    )
