from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Application,
    ApplicationStatus,
    Company,
    CompanyApprovalStatus,
    DriveStatus,
    JobPosition,
    Student,
    User,
    UserRole,
)
from app.security import token_required

admin_bp = Blueprint("admin", __name__)


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _parse_enum(value, enum_cls):
    if value is None:
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError:
        return None


def _serialize_company(company: Company):
    user = company.user
    return {
        "id": company.id,
        "user_id": company.user_id,
        "company_name": company.company_name,
        "industry": company.industry,
        "location": company.location,
        "hr_contact": company.hr_contact,
        "website": company.website,
        "approval_status": company.approval_status.value,
        "is_active": company.is_active,
        "email": user.email if user else None,
        "user_is_active": user.is_active if user else False,
        "user_is_blacklisted": user.is_blacklisted if user else False,
        "job_postings_count": len(company.job_positions),
        "created_at": company.created_at.isoformat(),
    }


def _serialize_student(student: Student):
    user = student.user
    return {
        "id": student.id,
        "user_id": student.user_id,
        "full_name": student.full_name,
        "education": student.education,
        "branch": student.branch,
        "graduation_year": student.graduation_year,
        "cgpa": student.cgpa,
        "contact_number": student.contact_number,
        "email": user.email if user else None,
        "is_active": student.is_active,
        "user_is_active": user.is_active if user else False,
        "user_is_blacklisted": user.is_blacklisted if user else False,
        "applications_count": len(student.applications),
        "created_at": student.created_at.isoformat(),
    }


def _serialize_drive(drive: JobPosition):
    company = drive.company
    return {
        "id": drive.id,
        "company_id": drive.company_id,
        "company_name": company.company_name if company else None,
        "title": drive.title,
        "description": drive.description,
        "salary": float(drive.salary) if drive.salary is not None else None,
        "skills_required": drive.skills_required,
        "minimum_cgpa": drive.minimum_cgpa,
        "application_deadline": drive.application_deadline.isoformat(),
        "status": drive.status.value,
        "applications_count": len(drive.applications),
        "created_at": drive.created_at.isoformat(),
    }


def _serialize_application(application: Application):
    student = application.student
    drive = application.job_position
    company = drive.company if drive else None
    return {
        "id": application.id,
        "student_id": application.student_id,
        "student_name": student.full_name if student else None,
        "student_contact": student.contact_number if student else None,
        "student_email": student.user.email if student and student.user else None,
        "job_id": application.job_id,
        "job_title": drive.title if drive else None,
        "company_id": company.id if company else None,
        "company_name": company.company_name if company else None,
        "status": application.status.value,
        "applied_at": application.applied_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
    }


@admin_bp.get("/overview")
@token_required(UserRole.ADMIN)
def overview():
    return jsonify(
        {
            "summary": {
                "students": Student.query.count(),
                "companies": Company.query.count(),
                "job_postings": JobPosition.query.count(),
                "applications": Application.query.count(),
            },
            "pending_approvals": {
                "companies": Company.query.filter_by(
                    approval_status=CompanyApprovalStatus.PENDING
                ).count(),
                "drives": JobPosition.query.filter_by(status=DriveStatus.PENDING).count(),
            },
            "inactive_or_blacklisted": {
                "students": Student.query.join(User)
                .filter(or_(Student.is_active.is_(False), User.is_blacklisted.is_(True)))
                .count(),
                "companies": Company.query.join(User)
                .filter(
                    or_(
                        Company.is_active.is_(False),
                        User.is_blacklisted.is_(True),
                        Company.approval_status == CompanyApprovalStatus.BLACKLISTED,
                    )
                )
                .count(),
            },
        }
    )


@admin_bp.get("/companies")
@token_required(UserRole.ADMIN)
def list_companies():
    query = Company.query.join(User, Company.user_id == User.id)

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            Company.company_name.ilike(like_value),
            Company.industry.ilike(like_value),
            Company.hr_contact.ilike(like_value),
            User.email.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(Company.id == int(search_text))
        query = query.filter(or_(*search_filters))

    industry_filter = (request.args.get("industry") or "").strip()
    if industry_filter:
        query = query.filter(Company.industry.ilike(f"%{industry_filter}%"))

    approval_status_filter = _parse_enum(
        request.args.get("approval_status"),
        CompanyApprovalStatus,
    )
    if request.args.get("approval_status") and not approval_status_filter:
        return jsonify({"error": "Invalid approval_status"}), 400
    if approval_status_filter:
        query = query.filter(Company.approval_status == approval_status_filter)

    companies = query.order_by(Company.created_at.desc()).all()
    return jsonify({"companies": [_serialize_company(company) for company in companies]})


@admin_bp.patch("/companies/<int:company_id>/approval")
@token_required(UserRole.ADMIN)
def update_company_approval(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404

    payload = request.get_json(silent=True) or {}
    approval_status = _parse_enum(payload.get("approval_status"), CompanyApprovalStatus)
    if not approval_status:
        return jsonify({"error": "Valid approval_status is required"}), 400

    company.approval_status = approval_status
    if approval_status == CompanyApprovalStatus.BLACKLISTED:
        company.is_active = False
        company.user.is_active = False
        company.user.is_blacklisted = True
    if approval_status == CompanyApprovalStatus.APPROVED:
        company.user.is_blacklisted = False
        company.is_active = True
        company.user.is_active = True

    db.session.commit()
    return jsonify({"message": "Company approval updated", "company": _serialize_company(company)})


@admin_bp.patch("/companies/<int:company_id>/status")
@token_required(UserRole.ADMIN)
def update_company_status(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404

    payload = request.get_json(silent=True) or {}
    next_is_active = _parse_bool(payload.get("is_active"))
    next_is_blacklisted = _parse_bool(payload.get("is_blacklisted"))

    if next_is_active is None and next_is_blacklisted is None:
        return jsonify({"error": "is_active or is_blacklisted is required"}), 400

    if next_is_blacklisted is not None:
        company.user.is_blacklisted = next_is_blacklisted
        if next_is_blacklisted:
            company.approval_status = CompanyApprovalStatus.BLACKLISTED
            company.is_active = False
            company.user.is_active = False
        elif company.approval_status == CompanyApprovalStatus.BLACKLISTED:
            company.approval_status = CompanyApprovalStatus.PENDING

    if next_is_active is not None:
        if next_is_active and company.user.is_blacklisted:
            return jsonify({"error": "Cannot activate a blacklisted company"}), 400
        company.is_active = next_is_active
        company.user.is_active = next_is_active

    db.session.commit()
    return jsonify({"message": "Company status updated", "company": _serialize_company(company)})


@admin_bp.delete("/companies/<int:company_id>")
@token_required(UserRole.ADMIN)
def delete_company(company_id: int):
    company = db.session.get(Company, company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404
    if company.placements:
        return jsonify({"error": "Cannot remove company with placement records"}), 409

    user = company.user
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Company removed successfully"})


@admin_bp.get("/students")
@token_required(UserRole.ADMIN)
def list_students():
    query = Student.query.join(User, Student.user_id == User.id)

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            Student.full_name.ilike(like_value),
            Student.contact_number.ilike(like_value),
            User.email.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(Student.id == int(search_text))
        query = query.filter(or_(*search_filters))

    students = query.order_by(Student.created_at.desc()).all()
    return jsonify({"students": [_serialize_student(student) for student in students]})


@admin_bp.patch("/students/<int:student_id>/status")
@token_required(UserRole.ADMIN)
def update_student_status(student_id: int):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404

    payload = request.get_json(silent=True) or {}
    next_is_active = _parse_bool(payload.get("is_active"))
    next_is_blacklisted = _parse_bool(payload.get("is_blacklisted"))

    if next_is_active is None and next_is_blacklisted is None:
        return jsonify({"error": "is_active or is_blacklisted is required"}), 400

    if next_is_blacklisted is not None:
        student.user.is_blacklisted = next_is_blacklisted
        if next_is_blacklisted:
            student.is_active = False
            student.user.is_active = False

    if next_is_active is not None:
        if next_is_active and student.user.is_blacklisted:
            return jsonify({"error": "Cannot activate a blacklisted student"}), 400
        student.is_active = next_is_active
        student.user.is_active = next_is_active

    db.session.commit()
    return jsonify({"message": "Student status updated", "student": _serialize_student(student)})


@admin_bp.delete("/students/<int:student_id>")
@token_required(UserRole.ADMIN)
def delete_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Student not found"}), 404
    if student.placements:
        return jsonify({"error": "Cannot remove student with placement records"}), 409

    user = student.user
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Student removed successfully"})


@admin_bp.get("/drives")
@token_required(UserRole.ADMIN)
def list_drives():
    query = JobPosition.query.join(Company, JobPosition.company_id == Company.id)

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            JobPosition.title.ilike(like_value),
            JobPosition.description.ilike(like_value),
            Company.company_name.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(JobPosition.id == int(search_text))
        query = query.filter(or_(*search_filters))

    company_id = (request.args.get("company_id") or "").strip()
    if company_id:
        if not company_id.isdigit():
            return jsonify({"error": "company_id must be an integer"}), 400
        query = query.filter(JobPosition.company_id == int(company_id))

    drive_status_filter = _parse_enum(request.args.get("status"), DriveStatus)
    if request.args.get("status") and not drive_status_filter:
        return jsonify({"error": "Invalid drive status"}), 400
    if drive_status_filter:
        query = query.filter(JobPosition.status == drive_status_filter)

    drives = query.order_by(JobPosition.created_at.desc()).all()
    return jsonify({"drives": [_serialize_drive(drive) for drive in drives]})


@admin_bp.patch("/drives/<int:drive_id>/status")
@token_required(UserRole.ADMIN)
def update_drive_status(drive_id: int):
    drive = db.session.get(JobPosition, drive_id)
    if not drive:
        return jsonify({"error": "Drive not found"}), 404

    payload = request.get_json(silent=True) or {}
    next_status = _parse_enum(payload.get("status"), DriveStatus)
    if not next_status:
        return jsonify({"error": "Valid status is required"}), 400

    if next_status == DriveStatus.APPROVED:
        company = drive.company
        if not company:
            return jsonify({"error": "Company profile missing"}), 400
        if company.approval_status != CompanyApprovalStatus.APPROVED:
            return jsonify({"error": "Drive cannot be approved for unapproved company"}), 400
        if not company.is_active or not company.user.is_active or company.user.is_blacklisted:
            return jsonify({"error": "Drive cannot be approved for inactive/blacklisted company"}), 400

    drive.status = next_status
    db.session.commit()
    return jsonify({"message": "Drive status updated", "drive": _serialize_drive(drive)})


@admin_bp.delete("/drives/<int:drive_id>")
@token_required(UserRole.ADMIN)
def delete_drive(drive_id: int):
    drive = db.session.get(JobPosition, drive_id)
    if not drive:
        return jsonify({"error": "Drive not found"}), 404
    if drive.placements:
        return jsonify({"error": "Cannot remove drive with placement records"}), 409

    db.session.delete(drive)
    db.session.commit()
    return jsonify({"message": "Drive removed successfully"})


@admin_bp.get("/applications")
@token_required(UserRole.ADMIN)
def list_applications():
    query = (
        Application.query.join(Student, Application.student_id == Student.id)
        .join(JobPosition, Application.job_id == JobPosition.id)
        .join(Company, JobPosition.company_id == Company.id)
        .join(User, Student.user_id == User.id)
    )

    search_text = (request.args.get("q") or "").strip()
    if search_text:
        like_value = f"%{search_text}%"
        search_filters = [
            Student.full_name.ilike(like_value),
            Company.company_name.ilike(like_value),
            JobPosition.title.ilike(like_value),
            User.email.ilike(like_value),
        ]
        if search_text.isdigit():
            search_filters.append(Application.id == int(search_text))
        query = query.filter(or_(*search_filters))

    application_status_filter = _parse_enum(
        request.args.get("status"),
        ApplicationStatus,
    )
    if request.args.get("status") and not application_status_filter:
        return jsonify({"error": "Invalid application status"}), 400
    if application_status_filter:
        query = query.filter(Application.status == application_status_filter)

    student_id = (request.args.get("student_id") or "").strip()
    if student_id:
        if not student_id.isdigit():
            return jsonify({"error": "student_id must be an integer"}), 400
        query = query.filter(Application.student_id == int(student_id))

    job_id = (request.args.get("job_id") or "").strip()
    if job_id:
        if not job_id.isdigit():
            return jsonify({"error": "job_id must be an integer"}), 400
        query = query.filter(Application.job_id == int(job_id))

    applications = query.order_by(Application.applied_at.desc()).all()
    return jsonify({"applications": [_serialize_application(app) for app in applications]})


@admin_bp.patch("/applications/<int:application_id>/status")
@token_required(UserRole.ADMIN)
def update_application_status(application_id: int):
    application = db.session.get(Application, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    payload = request.get_json(silent=True) or {}
    next_status = _parse_enum(payload.get("status"), ApplicationStatus)
    if not next_status:
        return jsonify({"error": "Valid status is required"}), 400

    application.status = next_status
    db.session.commit()
    return jsonify(
        {
            "message": "Application status updated",
            "application": _serialize_application(application),
        }
    )


@admin_bp.delete("/applications/<int:application_id>")
@token_required(UserRole.ADMIN)
def delete_application(application_id: int):
    application = db.session.get(Application, application_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    if application.placement:
        return jsonify({"error": "Cannot remove application linked to placement"}), 409

    db.session.delete(application)
    db.session.commit()
    return jsonify({"message": "Application removed successfully"})
