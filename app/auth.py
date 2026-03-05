from __future__ import annotations

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from app.cache import (
    CACHE_NS_ADMIN_COMPANIES,
    CACHE_NS_ADMIN_STUDENTS,
    invalidate_cache_namespaces,
)
from app.extensions import db
from app.models import Company, CompanyApprovalStatus, Student, User, UserRole
from app.security import create_access_token, token_required

auth_bp = Blueprint("auth", __name__)


def _clean_email(value: str | None) -> str:
    return (value or "").strip().lower()


@auth_bp.post("/register/student")
def register_student():
    payload = request.get_json(silent=True) or {}
    email = _clean_email(payload.get("email"))
    password = (payload.get("password") or "").strip()
    full_name = (payload.get("full_name") or "").strip()

    if not email or not password or not full_name:
        return jsonify({"error": "email, password and full_name are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role=UserRole.STUDENT,
    )
    student = Student(
        user=user,
        full_name=full_name,
        education=(payload.get("education") or "").strip() or None,
        experience=(payload.get("experience") or "").strip() or None,
        contact_number=(payload.get("contact_number") or "").strip() or None,
        branch=(payload.get("branch") or "").strip() or None,
        graduation_year=payload.get("graduation_year"),
        cgpa=payload.get("cgpa"),
        skills=(payload.get("skills") or "").strip() or None,
        resume_url=(payload.get("resume_url") or "").strip() or None,
    )
    db.session.add_all([user, student])
    db.session.commit()
    invalidate_cache_namespaces(CACHE_NS_ADMIN_STUDENTS)

    return jsonify({"message": "Student registered successfully"}), 201


@auth_bp.post("/register/company")
def register_company():
    payload = request.get_json(silent=True) or {}
    email = _clean_email(payload.get("email"))
    password = (payload.get("password") or "").strip()
    company_name = (payload.get("company_name") or "").strip()

    if not email or not password or not company_name:
        return jsonify({"error": "email, password and company_name are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        role=UserRole.COMPANY,
    )
    company = Company(
        user=user,
        company_name=company_name,
        industry=(payload.get("industry") or "").strip() or None,
        location=(payload.get("location") or "").strip() or None,
        hr_contact=(payload.get("hr_contact") or "").strip() or None,
        website=(payload.get("website") or "").strip() or None,
        approval_status=CompanyApprovalStatus.PENDING,
    )
    db.session.add_all([user, company])
    db.session.commit()
    invalidate_cache_namespaces(CACHE_NS_ADMIN_COMPANIES)

    return jsonify(
        {
            "message": "Company registered. Awaiting admin approval before login.",
            "approval_status": company.approval_status.value,
        }
    ), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = _clean_email(payload.get("email"))
    password = (payload.get("password") or "").strip()

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active or user.is_blacklisted:
        return jsonify({"error": "User is inactive or blacklisted"}), 403

    if user.role == UserRole.COMPANY:
        company = user.company_profile
        if not company:
            return jsonify({"error": "Company profile not found"}), 403
        if not company.is_active:
            return jsonify({"error": "Company account is inactive"}), 403
        if company.approval_status != CompanyApprovalStatus.APPROVED:
            return jsonify({"error": "Company is not approved by admin yet"}), 403

    if user.role == UserRole.STUDENT:
        student = user.student_profile
        if not student:
            return jsonify({"error": "Student profile not found"}), 403
        if not student.is_active:
            return jsonify({"error": "Student account is inactive"}), 403

    token = create_access_token(user)
    role = user.role.value
    return jsonify(
        {
            "access_token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "role": role,
            },
            "redirect_to": f"/#{role}-dashboard",
        }
    )


@auth_bp.get("/me")
@token_required(UserRole.ADMIN, UserRole.COMPANY, UserRole.STUDENT)
def me():
    from flask import g

    user = g.current_user
    response = {
        "id": user.id,
        "email": user.email,
        "role": user.role.value,
    }

    if user.role == UserRole.COMPANY and user.company_profile:
        response["company"] = {
            "id": user.company_profile.id,
            "company_name": user.company_profile.company_name,
            "approval_status": user.company_profile.approval_status.value,
        }

    if user.role == UserRole.STUDENT and user.student_profile:
        response["student"] = {
            "id": user.student_profile.id,
            "full_name": user.student_profile.full_name,
            "education": user.student_profile.education,
            "experience": user.student_profile.experience,
            "contact_number": user.student_profile.contact_number,
            "branch": user.student_profile.branch,
            "graduation_year": user.student_profile.graduation_year,
            "cgpa": user.student_profile.cgpa,
        }

    return jsonify(response)
