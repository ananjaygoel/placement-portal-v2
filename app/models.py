from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import UniqueConstraint

from app.extensions import db


class UserRole(str, Enum):
    ADMIN = "admin"
    COMPANY = "company"
    STUDENT = "student"


class CompanyApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLACKLISTED = "blacklisted"


class DriveStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CLOSED = "closed"
    REJECTED = "rejected"


class ApplicationStatus(str, Enum):
    APPLIED = "applied"
    SHORTLISTED = "shortlisted"
    SELECTED = "selected"
    REJECTED = "rejected"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(SAEnum(UserRole, native_enum=False), nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_blacklisted = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    company_profile = db.relationship(
        "Company",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    student_profile = db.relationship(
        "Student",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company_name = db.Column(db.String(255), nullable=False, index=True)
    industry = db.Column(db.String(120))
    location = db.Column(db.String(120))
    hr_contact = db.Column(db.String(120))
    website = db.Column(db.String(255))
    approval_status = db.Column(
        SAEnum(CompanyApprovalStatus, native_enum=False),
        default=CompanyApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", back_populates="company_profile")
    job_positions = db.relationship(
        "JobPosition",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    placements = db.relationship("Placement", back_populates="company")


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(255), nullable=False, index=True)
    education = db.Column(db.String(255))
    contact_number = db.Column(db.String(30), index=True)
    branch = db.Column(db.String(120), index=True)
    graduation_year = db.Column(db.Integer, index=True)
    cgpa = db.Column(db.Float)
    skills = db.Column(db.Text)
    resume_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", back_populates="student_profile")
    applications = db.relationship(
        "Application",
        back_populates="student",
        cascade="all, delete-orphan",
    )
    placements = db.relationship("Placement", back_populates="student")


class JobPosition(db.Model):
    __tablename__ = "job_positions"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False, index=True)
    description = db.Column(db.Text)
    salary = db.Column(db.Numeric(12, 2))
    skills_required = db.Column(db.Text)
    eligibility_branch = db.Column(db.String(120), index=True)
    minimum_cgpa = db.Column(db.Float)
    minimum_graduation_year = db.Column(db.Integer)
    application_deadline = db.Column(db.Date, default=date.today, nullable=False, index=True)
    status = db.Column(
        SAEnum(DriveStatus, native_enum=False),
        default=DriveStatus.PENDING,
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    company = db.relationship("Company", back_populates="job_positions")
    applications = db.relationship(
        "Application",
        back_populates="job_position",
        cascade="all, delete-orphan",
    )
    placements = db.relationship("Placement", back_populates="job_position")


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("student_id", "job_id", name="uq_student_job_application"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_positions.id"), nullable=False, index=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(
        SAEnum(ApplicationStatus, native_enum=False),
        default=ApplicationStatus.APPLIED,
        nullable=False,
        index=True,
    )
    notes = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    student = db.relationship("Student", back_populates="applications")
    job_position = db.relationship("JobPosition", back_populates="applications")
    placement = db.relationship("Placement", back_populates="application", uselist=False)


class Placement(db.Model):
    __tablename__ = "placements"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_positions.id"), index=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("applications.id"),
        unique=True,
        nullable=True,
        index=True,
    )
    position_title = db.Column(db.String(255), nullable=False)
    salary = db.Column(db.Numeric(12, 2))
    joining_date = db.Column(db.Date, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", back_populates="placements")
    company = db.relationship("Company", back_populates="placements")
    job_position = db.relationship("JobPosition", back_populates="placements")
    application = db.relationship("Application", back_populates="placement")
