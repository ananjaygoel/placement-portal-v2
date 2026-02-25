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
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    PLACED = "placed"
    SELECTED = "selected"


class InterviewStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AsyncJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportScope(str, Enum):
    STUDENT_HISTORY = "student_history"
    COMPANY_HISTORY = "company_history"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    GCHAT = "gchat"
    SMS = "sms"
    IN_APP = "in_app"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ReportFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"


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
    export_jobs = db.relationship(
        "AsyncExportJob",
        back_populates="requester_user",
        cascade="all, delete-orphan",
    )
    notifications = db.relationship(
        "Notification",
        back_populates="user",
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
    interviews = db.relationship(
        "Interview",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    placements = db.relationship("Placement", back_populates="company")
    placement_reports = db.relationship(
        "PlacementReport",
        back_populates="company",
        cascade="all, delete-orphan",
    )


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(255), nullable=False, index=True)
    education = db.Column(db.String(255))
    experience = db.Column(db.Text)
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
    experience_required = db.Column(db.String(120))
    benefits = db.Column(db.Text)
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
    company_feedback = db.Column(db.Text)
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
    interviews = db.relationship(
        "Interview",
        back_populates="application",
        cascade="all, delete-orphan",
    )
    status_history = db.relationship(
        "ApplicationStatusHistory",
        back_populates="application",
        cascade="all, delete-orphan",
    )


class ApplicationStatusHistory(db.Model):
    __tablename__ = "application_status_history"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("applications.id"),
        nullable=False,
        index=True,
    )
    previous_status = db.Column(
        SAEnum(ApplicationStatus, native_enum=False),
        nullable=True,
    )
    new_status = db.Column(
        SAEnum(ApplicationStatus, native_enum=False),
        nullable=False,
        index=True,
    )
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    changed_by_role = db.Column(
        SAEnum(UserRole, native_enum=False),
        nullable=False,
        index=True,
    )
    remarks = db.Column(db.Text)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    application = db.relationship("Application", back_populates="status_history")
    changed_by_user = db.relationship("User")


class Interview(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer,
        db.ForeignKey("applications.id"),
        nullable=False,
        index=True,
    )
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    scheduled_at = db.Column(db.DateTime, nullable=False, index=True)
    interview_mode = db.Column(db.String(50), nullable=False, default="virtual")
    meeting_link = db.Column(db.String(255))
    location = db.Column(db.String(255))
    notes = db.Column(db.Text)
    last_reminder_sent_at = db.Column(db.DateTime)
    status = db.Column(
        SAEnum(InterviewStatus, native_enum=False),
        default=InterviewStatus.SCHEDULED,
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

    application = db.relationship("Application", back_populates="interviews")
    company = db.relationship("Company", back_populates="interviews")


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


class AsyncExportJob(db.Model):
    __tablename__ = "async_export_jobs"

    id = db.Column(db.Integer, primary_key=True)
    requester_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    requested_by_role = db.Column(
        SAEnum(UserRole, native_enum=False),
        nullable=False,
        index=True,
    )
    scope = db.Column(
        SAEnum(ExportScope, native_enum=False),
        nullable=False,
        index=True,
    )
    status = db.Column(
        SAEnum(AsyncJobStatus, native_enum=False),
        default=AsyncJobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    celery_task_id = db.Column(db.String(120), index=True)
    file_name = db.Column(db.String(255))
    file_path = db.Column(db.String(500))
    row_count = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    metadata_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    requester_user = db.relationship("User", back_populates="export_jobs")
    notifications = db.relationship("Notification", back_populates="export_job")


class PlacementReport(db.Model):
    __tablename__ = "placement_reports"
    __table_args__ = (
        UniqueConstraint("company_id", "month_label", "report_format", name="uq_company_month_format_report"),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    month_label = db.Column(db.String(20), nullable=False, index=True)
    report_format = db.Column(
        SAEnum(ReportFormat, native_enum=False),
        nullable=False,
        index=True,
    )
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    summary_json = db.Column(db.JSON)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    celery_task_id = db.Column(db.String(120), index=True)

    company = db.relationship("Company", back_populates="placement_reports")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    channel = db.Column(
        SAEnum(NotificationChannel, native_enum=False),
        default=NotificationChannel.IN_APP,
        nullable=False,
        index=True,
    )
    status = db.Column(
        SAEnum(NotificationStatus, native_enum=False),
        default=NotificationStatus.SENT,
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    related_job_id = db.Column(
        db.Integer,
        db.ForeignKey("async_export_jobs.id"),
        index=True,
    )
    delivery_response = db.Column(db.Text)
    metadata_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="notifications")
    export_job = db.relationship("AsyncExportJob", back_populates="notifications")
