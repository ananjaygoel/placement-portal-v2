from __future__ import annotations

from datetime import date

from flask import Blueprint, g, jsonify

from app.models import (
    Application,
    ApplicationStatus,
    Company,
    CompanyApprovalStatus,
    DriveStatus,
    JobPosition,
    Placement,
    Student,
    UserRole,
)
from app.security import token_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/admin")
@token_required(UserRole.ADMIN)
def admin_dashboard():
    return jsonify(
        {
            "role": "admin",
            "summary": {
                "students": Student.query.count(),
                "companies": Company.query.count(),
                "job_postings": JobPosition.query.count(),
                "placement_drives": JobPosition.query.count(),
                "applications": Application.query.count(),
                "placements": Placement.query.count(),
            },
            "pending_approvals": {
                "companies": Company.query.filter_by(
                    approval_status=CompanyApprovalStatus.PENDING
                ).count(),
                "drives": JobPosition.query.filter_by(status=DriveStatus.PENDING).count(),
            },
        }
    )


@dashboard_bp.get("/company")
@token_required(UserRole.COMPANY)
def company_dashboard():
    user = g.current_user
    company = user.company_profile
    if not company:
        return jsonify({"error": "Company profile not found"}), 404
    if company.approval_status != CompanyApprovalStatus.APPROVED:
        return jsonify({"error": "Company is not approved by admin"}), 403
    if not company.is_active or not user.is_active or user.is_blacklisted:
        return jsonify({"error": "Company account is inactive or blacklisted"}), 403

    drives = []
    for drive in company.job_positions:
        applicants_count = Application.query.filter_by(job_id=drive.id).count()
        shortlisted_count = Application.query.filter_by(
            job_id=drive.id,
            status=ApplicationStatus.SHORTLISTED,
        ).count()
        selected_count = Application.query.filter_by(
            job_id=drive.id,
            status=ApplicationStatus.SELECTED,
        ).count()
        drives.append(
            {
                "id": drive.id,
                "title": drive.title,
                "skills_required": drive.skills_required,
                "experience_required": drive.experience_required,
                "benefits": drive.benefits,
                "status": drive.status.value,
                "application_deadline": drive.application_deadline.isoformat(),
                "applicants_count": applicants_count,
                "shortlisted_count": shortlisted_count,
                "selected_count": selected_count,
            }
        )

    total_applications = (
        Application.query.join(JobPosition)
        .filter(JobPosition.company_id == company.id)
        .count()
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
                "job_postings": len(drives),
                "received_applications": total_applications,
                "shortlisted_candidates": (
                    Application.query.join(JobPosition)
                    .filter(
                        JobPosition.company_id == company.id,
                        Application.status == ApplicationStatus.SHORTLISTED,
                    )
                    .count()
                ),
                "selected_candidates": (
                    Application.query.join(JobPosition)
                    .filter(
                        JobPosition.company_id == company.id,
                        Application.status == ApplicationStatus.SELECTED,
                    )
                    .count()
                ),
            },
            "drives": drives,
        }
    )


@dashboard_bp.get("/student")
@token_required(UserRole.STUDENT)
def student_dashboard():
    user = g.current_user
    student = user.student_profile
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    approved_drives = (
        JobPosition.query.filter(
            JobPosition.status == DriveStatus.APPROVED,
            JobPosition.application_deadline >= date.today(),
        )
        .order_by(JobPosition.application_deadline.asc())
        .all()
    )

    drives_payload = [
        {
            "id": drive.id,
            "company_name": drive.company.company_name,
            "title": drive.title,
            "minimum_cgpa": drive.minimum_cgpa,
            "application_deadline": drive.application_deadline.isoformat(),
        }
        for drive in approved_drives
    ]

    application_history = [
        {
            "application_id": application.id,
            "job_id": application.job_id,
            "job_title": application.job_position.title,
            "company_name": application.job_position.company.company_name,
            "status": application.status.value,
            "company_feedback": application.company_feedback,
            "applied_at": application.applied_at.isoformat(),
            "latest_interview_at": (
                max(
                    [interview.scheduled_at for interview in application.interviews],
                    default=None,
                ).isoformat()
                if application.interviews
                else None
            ),
        }
        for application in student.applications
    ]

    return jsonify(
        {
            "role": "student",
            "student": {
                "id": student.id,
                "full_name": student.full_name,
                "contact_number": student.contact_number,
                "branch": student.branch,
                "graduation_year": student.graduation_year,
                "cgpa": student.cgpa,
            },
            "approved_drives": drives_payload,
            "application_history": application_history,
        }
    )
