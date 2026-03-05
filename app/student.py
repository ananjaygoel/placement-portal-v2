from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import or_

from app.application_tracking import (
    append_status_history,
    serialize_status_history,
)
from app.cache import (
    CACHE_NS_ADMIN_STUDENTS,
    CACHE_NS_STUDENT_JOBS,
    invalidate_cache_namespaces,
    load_cached_json,
)
from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    AsyncExportJob,
    AsyncJobStatus,
    Company,
    CompanyApprovalStatus,
    DriveStatus,
    ExportScope,
    Interview,
    InterviewStatus,
    JobPosition,
    Notification,
    Student,
    User,
    UserRole,
)
from app.security import token_required
from app.tasks import process_export_job_task

student_bp = Blueprint("student", __name__)


def _parse_enum(value, enum_cls):
    if value is None:
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return None


def _ensure_student_access():
    user = g.current_user
    student = user.student_profile
    if not student:
        return None, (jsonify({"error": "Student profile not found"}), 404)
    if not student.is_active or not user.is_active or user.is_blacklisted:
        return None, (jsonify({"error": "Student account is inactive or blacklisted"}), 403)
    return student, None


def _job_visibility_query():
    return (
        JobPosition.query.join(Company, JobPosition.company_id == Company.id)
        .join(User, Company.user_id == User.id)
        .filter(
            JobPosition.status == DriveStatus.APPROVED,
            Company.approval_status == CompanyApprovalStatus.APPROVED,
            Company.is_active.is_(True),
            User.is_active.is_(True),
            User.is_blacklisted.is_(False),
        )
    )


def _split_branches(branch_value: str):
    normalized = branch_value.replace("|", ",").replace("/", ",")
    return [branch.strip().lower() for branch in normalized.split(",") if branch.strip()]


def _eligibility_for_job(student: Student, job: JobPosition):
    reasons = []

    if job.eligibility_branch:
        eligible_branches = _split_branches(job.eligibility_branch)
        student_branch = (student.branch or "").strip().lower()
        if not student_branch:
            reasons.append("Student branch is missing")
        elif eligible_branches and student_branch not in eligible_branches:
            reasons.append(
                f"Branch '{student.branch}' is not eligible for this job"
            )

    if job.minimum_cgpa is not None:
        if student.cgpa is None:
            reasons.append("Student CGPA is missing")
        elif student.cgpa < job.minimum_cgpa:
            reasons.append(
                f"Minimum CGPA required is {job.minimum_cgpa}, student has {student.cgpa}"
            )

    if job.minimum_graduation_year is not None:
        if student.graduation_year is None:
            reasons.append("Student graduation year is missing")
        elif student.graduation_year < job.minimum_graduation_year:
            reasons.append(
                f"Minimum graduation year is {job.minimum_graduation_year}"
            )

    return len(reasons) == 0, reasons


def _serialize_interview_for_student(interview: Interview):
    application = interview.application
    job = application.job_position if application else None
    company = job.company if job else None
    return {
        "id": interview.id,
        "application_id": interview.application_id,
        "job_id": application.job_id if application else None,
        "job_title": job.title if job else None,
        "company_name": company.company_name if company else None,
        "scheduled_at": interview.scheduled_at.isoformat(),
        "interview_mode": interview.interview_mode,
        "meeting_link": interview.meeting_link,
        "location": interview.location,
        "notes": interview.notes,
        "status": interview.status.value,
    }


def _serialize_job_for_student(
    student: Student,
    job: JobPosition,
    applied_by_job_id: dict[int, Application],
):
    is_eligible, eligibility_reasons = _eligibility_for_job(student, job)
    existing_application = applied_by_job_id.get(job.id)
    return {
        "id": job.id,
        "company_id": job.company_id,
        "company_name": job.company.company_name if job.company else None,
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
        "is_eligible": is_eligible,
        "eligibility_reasons": eligibility_reasons,
        "already_applied": existing_application is not None,
        "application_status": (
            existing_application.status.value if existing_application else None
        ),
    }


def _serialize_application_for_student(application: Application):
    job = application.job_position
    company = job.company if job else None
    interviews = sorted(
        application.interviews,
        key=lambda interview: interview.scheduled_at,
    )
    placement = application.placement
    offer_letter_available = (
        application.status in {
            ApplicationStatus.OFFER,
            ApplicationStatus.SELECTED,
            ApplicationStatus.PLACED,
        }
        or placement is not None
    )
    placement_confirmation_available = (
        placement is not None
        or application.status
        in {ApplicationStatus.OFFER, ApplicationStatus.SELECTED, ApplicationStatus.PLACED}
    )
    return {
        "id": application.id,
        "job_id": application.job_id,
        "job_title": job.title if job else None,
        "company_id": company.id if company else None,
        "company_name": company.company_name if company else None,
        "status": application.status.value,
        "company_feedback": application.company_feedback,
        "applied_at": application.applied_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
        "interviews": [_serialize_interview_for_student(interview) for interview in interviews],
        "latest_interview": (
            _serialize_interview_for_student(interviews[-1]) if interviews else None
        ),
        "status_history": [
            serialize_status_history(record)
            for record in sorted(
                application.status_history,
                key=lambda history: history.changed_at,
            )
        ],
        "offer_letter_available": offer_letter_available,
        "placement_confirmation_available": placement_confirmation_available,
        "placement": (
            {
                "id": placement.id,
                "position_title": placement.position_title,
                "salary": float(placement.salary) if placement.salary is not None else None,
                "joining_date": placement.joining_date.isoformat(),
            }
            if placement
            else None
        ),
    }


def _serialize_export_job(export_job: AsyncExportJob):
    return {
        "id": export_job.id,
        "scope": export_job.scope.value,
        "status": export_job.status.value,
        "celery_task_id": export_job.celery_task_id,
        "file_name": export_job.file_name,
        "row_count": export_job.row_count,
        "error_message": export_job.error_message,
        "created_at": export_job.created_at.isoformat(),
        "started_at": export_job.started_at.isoformat() if export_job.started_at else None,
        "completed_at": export_job.completed_at.isoformat() if export_job.completed_at else None,
    }


def _serialize_notification(notification: Notification):
    return {
        "id": notification.id,
        "title": notification.title,
        "message": notification.message,
        "channel": notification.channel.value,
        "status": notification.status.value,
        "is_read": notification.is_read,
        "related_job_id": notification.related_job_id,
        "created_at": notification.created_at.isoformat(),
    }


def _render_offer_letter(application: Application):
    student = application.student
    company = application.job_position.company
    job = application.job_position
    joining_date = (
        application.placement.joining_date.isoformat()
        if application.placement
        else "To be communicated"
    )
    salary_text = (
        str(float(application.placement.salary))
        if application.placement and application.placement.salary is not None
        else (str(float(job.salary)) if job.salary is not None else "As per policy")
    )

    lines = [
        "Placement Portal Application - Offer Letter",
        f"Issue Date: {date.today().isoformat()}",
        "",
        f"Candidate: {student.full_name}",
        f"Company: {company.company_name}",
        f"Position: {job.title}",
        f"Compensation: {salary_text}",
        f"Expected Joining Date: {joining_date}",
        "",
        "Congratulations! Your application is offered/placed.",
        "Please coordinate with HR for onboarding formalities.",
    ]
    return "\n".join(lines)


def _render_placement_confirmation(application: Application):
    student = application.student
    company = application.job_position.company
    job = application.job_position
    placement = application.placement

    lines = [
        "Placement Portal Application - Placement Confirmation",
        f"Generated Date: {date.today().isoformat()}",
        "",
        f"Student Name: {student.full_name}",
        f"Student ID: {student.id}",
        f"Company: {company.company_name}",
        f"Position: {job.title}",
        f"Application Status: {application.status.value}",
    ]
    if placement:
        lines.extend(
            [
                f"Placement ID: {placement.id}",
                f"Joining Date: {placement.joining_date.isoformat()}",
                (
                    f"Final Salary: {float(placement.salary)}"
                    if placement.salary is not None
                    else "Final Salary: As communicated"
                ),
            ]
        )
    else:
        lines.append("Placement record is pending final institute confirmation.")
    lines.extend(
        [
            "",
            "This document is generated from the Placement Portal Application.",
        ]
    )
    return "\n".join(lines)


def _document_response(content: str, filename: str):
    payload = BytesIO(content.encode("utf-8"))
    return send_file(
        payload,
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain",
    )


@student_bp.get("/overview")
@token_required(UserRole.STUDENT)
def student_overview():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    user = g.current_user
    available_jobs_count = _job_visibility_query().filter(
        JobPosition.application_deadline >= date.today()
    ).count()
    applications = (
        Application.query.filter_by(student_id=student.id)
        .order_by(Application.applied_at.desc())
        .all()
    )
    interviews = (
        Interview.query.join(Application, Interview.application_id == Application.id)
        .filter(Application.student_id == student.id)
        .order_by(Interview.scheduled_at.asc())
        .all()
    )

    return jsonify(
        {
            "role": "student",
            "student": {
                "id": student.id,
                "full_name": student.full_name,
                "education": student.education,
                "experience": student.experience,
                "skills": student.skills,
                "resume_url": student.resume_url,
                "branch": student.branch,
                "graduation_year": student.graduation_year,
                "cgpa": student.cgpa,
                "contact_number": student.contact_number,
                "email": student.user.email if student.user else None,
            },
            "summary": {
                "available_jobs": available_jobs_count,
                "applied_jobs": len(applications),
                "shortlisted_jobs": sum(
                    1
                    for application in applications
                    if application.status in {
                        ApplicationStatus.SHORTLISTED,
                        ApplicationStatus.INTERVIEW,
                    }
                ),
                "offered_jobs": sum(
                    1
                    for application in applications
                    if application.status in {
                        ApplicationStatus.OFFER,
                        ApplicationStatus.SELECTED,
                    }
                ),
                "placed_jobs": sum(
                    1
                    for application in applications
                    if application.status == ApplicationStatus.PLACED
                ),
                "rejected_jobs": sum(
                    1
                    for application in applications
                    if application.status == ApplicationStatus.REJECTED
                ),
                "scheduled_interviews": sum(
                    1
                    for interview in interviews
                    if interview.status == InterviewStatus.SCHEDULED
                ),
                "pending_exports": AsyncExportJob.query.filter_by(
                    requester_user_id=user.id,
                )
                .filter(
                    AsyncExportJob.status.in_(
                        [AsyncJobStatus.QUEUED, AsyncJobStatus.RUNNING]
                    )
                )
                .count(),
                "unread_notifications": Notification.query.filter_by(
                    user_id=user.id,
                    is_read=False,
                ).count(),
            },
            "recent_applications": [
                _serialize_application_for_student(application)
                for application in applications[:10]
            ],
            "placement_history": [
                {
                    "placement_id": placement.id,
                    "company_name": placement.company.company_name if placement.company else None,
                    "position_title": placement.position_title,
                    "salary": float(placement.salary) if placement.salary is not None else None,
                    "joining_date": placement.joining_date.isoformat(),
                }
                for placement in sorted(
                    student.placements,
                    key=lambda placement_record: placement_record.joining_date,
                    reverse=True,
                )
            ],
            "upcoming_interviews": [
                _serialize_interview_for_student(interview)
                for interview in interviews
                if interview.status == InterviewStatus.SCHEDULED
                and interview.scheduled_at >= datetime.utcnow()
            ][:10],
        }
    )


@student_bp.patch("/profile")
@token_required(UserRole.STUDENT)
def update_profile():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}

    if "full_name" in payload:
        next_name = (payload.get("full_name") or "").strip()
        if not next_name:
            return jsonify({"error": "full_name cannot be empty"}), 400
        student.full_name = next_name

    if "education" in payload:
        student.education = (payload.get("education") or "").strip() or None
    if "skills" in payload:
        student.skills = (payload.get("skills") or "").strip() or None
    if "resume_url" in payload:
        student.resume_url = (payload.get("resume_url") or "").strip() or None
    if "experience" in payload:
        student.experience = (payload.get("experience") or "").strip() or None
    if "contact_number" in payload:
        student.contact_number = (payload.get("contact_number") or "").strip() or None
    if "branch" in payload:
        student.branch = (payload.get("branch") or "").strip() or None
    if "graduation_year" in payload:
        student.graduation_year = payload.get("graduation_year")
    if "cgpa" in payload:
        student.cgpa = payload.get("cgpa")

    db.session.commit()
    invalidate_cache_namespaces(CACHE_NS_ADMIN_STUDENTS, CACHE_NS_STUDENT_JOBS)

    return jsonify(
        {
            "message": "Student profile updated",
            "student": {
                "id": student.id,
                "full_name": student.full_name,
                "education": student.education,
                "experience": student.experience,
                "skills": student.skills,
                "resume_url": student.resume_url,
                "branch": student.branch,
                "graduation_year": student.graduation_year,
                "cgpa": student.cgpa,
                "contact_number": student.contact_number,
            },
        }
    )


@student_bp.get("/jobs")
@token_required(UserRole.STUDENT)
def list_jobs():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    def _load_jobs_payload():
        query = _job_visibility_query().filter(JobPosition.application_deadline >= date.today())
        search_text = (request.args.get("q") or "").strip()
        if search_text:
            like_value = f"%{search_text}%"
            query = query.filter(
                or_(
                    Company.company_name.ilike(like_value),
                    JobPosition.title.ilike(like_value),
                    JobPosition.skills_required.ilike(like_value),
                    JobPosition.experience_required.ilike(like_value),
                )
            )

        company_filter = (request.args.get("company") or "").strip()
        if company_filter:
            query = query.filter(Company.company_name.ilike(f"%{company_filter}%"))

        position_filter = (request.args.get("position") or "").strip()
        if position_filter:
            query = query.filter(JobPosition.title.ilike(f"%{position_filter}%"))

        skills_filter = (request.args.get("skills") or "").strip()
        if skills_filter:
            query = query.filter(JobPosition.skills_required.ilike(f"%{skills_filter}%"))

        jobs = query.order_by(JobPosition.application_deadline.asc()).all()
        applications = Application.query.filter_by(student_id=student.id).all()
        applied_by_job_id = {application.job_id: application for application in applications}

        return {
            "jobs": [
                _serialize_job_for_student(student, job, applied_by_job_id) for job in jobs
            ]
        }

    payload, is_cache_hit = load_cached_json(
        namespace=CACHE_NS_STUDENT_JOBS,
        params=request.args.to_dict(flat=True),
        ttl_seconds=current_app.config["CACHE_JOB_LIST_TTL_SECONDS"],
        loader=_load_jobs_payload,
        user_scope=f"student:{g.current_user.id}",
    )
    response = jsonify(payload)
    response.headers["X-Cache"] = "HIT" if is_cache_hit else "MISS"
    return response


@student_bp.post("/jobs/<int:job_id>/apply")
@token_required(UserRole.STUDENT)
def apply_to_job(job_id: int):
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    job = (
        _job_visibility_query()
        .filter(
            JobPosition.id == job_id,
            JobPosition.application_deadline >= date.today(),
        )
        .first()
    )
    if not job:
        return jsonify({"error": "Job is not available for applications"}), 404

    existing_application = Application.query.filter_by(
        student_id=student.id,
        job_id=job.id,
    ).first()
    if existing_application:
        return jsonify({"error": "You have already applied to this job"}), 409

    is_eligible, eligibility_reasons = _eligibility_for_job(student, job)
    if not is_eligible:
        return (
            jsonify(
                {
                    "error": "Student does not meet eligibility criteria",
                    "reasons": eligibility_reasons,
                }
            ),
            400,
        )

    application = Application(
        student_id=student.id,
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
    )
    db.session.add(application)
    db.session.flush()
    append_status_history(
        application=application,
        previous_status=None,
        new_status=ApplicationStatus.APPLIED,
        changed_by_role=UserRole.STUDENT,
        changed_by_user_id=g.current_user.id,
        remarks="Application submitted",
    )
    db.session.commit()
    invalidate_cache_namespaces(CACHE_NS_STUDENT_JOBS)

    return jsonify(
        {
            "message": "Application submitted successfully",
            "application": _serialize_application_for_student(application),
        }
    ), 201


@student_bp.get("/applications")
@token_required(UserRole.STUDENT)
def list_applications():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    query = Application.query.filter_by(student_id=student.id)

    status_filter = _parse_enum(request.args.get("status"), ApplicationStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid application status"}), 400
    if status_filter:
        query = query.filter(Application.status == status_filter)

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        query = query.join(JobPosition, Application.job_id == JobPosition.id).join(
            Company, JobPosition.company_id == Company.id
        )
        query = query.filter(
            or_(
                JobPosition.title.ilike(like_value),
                Company.company_name.ilike(like_value),
            )
        )

    applications = query.order_by(Application.applied_at.desc()).all()
    return jsonify(
        {
            "applications": [
                _serialize_application_for_student(application)
                for application in applications
            ]
        }
    )


@student_bp.get("/interviews")
@token_required(UserRole.STUDENT)
def list_interviews():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    query = Interview.query.join(Application, Interview.application_id == Application.id).filter(
        Application.student_id == student.id
    )

    status_filter = _parse_enum(request.args.get("status"), InterviewStatus)
    if request.args.get("status") and not status_filter:
        return jsonify({"error": "Invalid interview status"}), 400
    if status_filter:
        query = query.filter(Interview.status == status_filter)

    interviews = query.order_by(Interview.scheduled_at.asc()).all()
    return jsonify(
        {
            "interviews": [
                _serialize_interview_for_student(interview) for interview in interviews
            ]
        }
    )


def _application_for_student(student_id: int, application_id: int):
    return Application.query.filter_by(id=application_id, student_id=student_id).first()


@student_bp.post("/exports")
@token_required(UserRole.STUDENT)
def request_student_export():
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}
    requested_scope = _parse_enum(payload.get("scope"), ExportScope)
    if payload.get("scope") and not requested_scope:
        return jsonify({"error": "Invalid export scope"}), 400

    scope = requested_scope or ExportScope.STUDENT_HISTORY
    if scope != ExportScope.STUDENT_HISTORY:
        return jsonify({"error": "Students can only export student_history scope"}), 400

    export_job = AsyncExportJob(
        requester_user_id=g.current_user.id,
        requested_by_role=UserRole.STUDENT,
        scope=scope,
        status=AsyncJobStatus.QUEUED,
        metadata_json={"student_id": student.id},
    )
    db.session.add(export_job)
    db.session.commit()

    task = process_export_job_task.delay(export_job.id)
    export_job.celery_task_id = task.id
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Export job queued successfully",
                "export_job": _serialize_export_job(export_job),
            }
        ),
        202,
    )


@student_bp.get("/exports")
@token_required(UserRole.STUDENT)
def list_student_exports():
    _, error_response = _ensure_student_access()
    if error_response:
        return error_response

    exports = (
        AsyncExportJob.query.filter_by(
            requester_user_id=g.current_user.id,
            requested_by_role=UserRole.STUDENT,
        )
        .order_by(AsyncExportJob.created_at.desc())
        .all()
    )
    return jsonify({"exports": [_serialize_export_job(export_job) for export_job in exports]})


@student_bp.get("/exports/<int:export_job_id>/download")
@token_required(UserRole.STUDENT)
def download_student_export(export_job_id: int):
    _, error_response = _ensure_student_access()
    if error_response:
        return error_response

    export_job = db.session.get(AsyncExportJob, export_job_id)
    if not export_job or export_job.requester_user_id != g.current_user.id:
        return jsonify({"error": "Export job not found"}), 404
    if export_job.status != AsyncJobStatus.COMPLETED:
        return jsonify({"error": "Export file is not ready yet"}), 409
    if not export_job.file_path:
        return jsonify({"error": "Export file path is missing"}), 409

    file_path = Path(export_job.file_path)
    if not file_path.exists():
        return jsonify({"error": "Export file not found on server"}), 404

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=export_job.file_name or file_path.name,
        mimetype="text/csv",
    )


@student_bp.get("/notifications")
@token_required(UserRole.STUDENT)
def list_student_notifications():
    _, error_response = _ensure_student_access()
    if error_response:
        return error_response

    notifications = (
        Notification.query.filter_by(user_id=g.current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "notifications": [
                _serialize_notification(notification) for notification in notifications
            ]
        }
    )


@student_bp.patch("/notifications/<int:notification_id>/read")
@token_required(UserRole.STUDENT)
def mark_student_notification_read(notification_id: int):
    _, error_response = _ensure_student_access()
    if error_response:
        return error_response

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=g.current_user.id,
    ).first()
    if not notification:
        return jsonify({"error": "Notification not found"}), 404

    notification.is_read = True
    db.session.commit()
    return jsonify(
        {
            "message": "Notification marked as read",
            "notification": _serialize_notification(notification),
        }
    )


@student_bp.get("/applications/<int:application_id>/offer-letter")
@token_required(UserRole.STUDENT)
def download_offer_letter(application_id: int):
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    application = _application_for_student(student.id, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404
    if (
        application.status
        not in {
            ApplicationStatus.OFFER,
            ApplicationStatus.SELECTED,
            ApplicationStatus.PLACED,
        }
        and application.placement is None
    ):
        return jsonify({"error": "Offer letter is available only after offer/placement"}), 400

    content = _render_offer_letter(application)
    filename = f"offer_letter_application_{application.id}.txt"
    return _document_response(content, filename)


@student_bp.get("/applications/<int:application_id>/placement-confirmation")
@token_required(UserRole.STUDENT)
def download_placement_confirmation(application_id: int):
    student, error_response = _ensure_student_access()
    if error_response:
        return error_response

    application = _application_for_student(student.id, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404
    if (
        application.status
        not in {
            ApplicationStatus.OFFER,
            ApplicationStatus.SELECTED,
            ApplicationStatus.PLACED,
        }
        and application.placement is None
    ):
        return jsonify(
            {"error": "Placement confirmation is available only after offer/placement"}
        ), 400

    content = _render_placement_confirmation(application)
    filename = f"placement_confirmation_application_{application.id}.txt"
    return _document_response(content, filename)
