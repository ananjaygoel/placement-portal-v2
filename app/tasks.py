from __future__ import annotations

import csv
import json
import smtplib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib import request as urllib_request
from urllib.error import URLError

from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import and_

from app.extensions import celery, db
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
    NotificationChannel,
    NotificationStatus,
    Placement,
    PlacementReport,
    ReportFormat,
    Student,
    User,
    UserRole,
)


@dataclass(frozen=True)
class MonthWindow:
    label: str
    start_date: date
    end_date: date
    start_dt: datetime
    end_dt: datetime


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_notification_channel(raw_value: str | None) -> NotificationChannel:
    cleaned = (raw_value or "").strip().lower()
    if not cleaned:
        return NotificationChannel.IN_APP
    try:
        return NotificationChannel(cleaned)
    except ValueError:
        return NotificationChannel.IN_APP


def _normalize_report_format(raw_value: str | None) -> ReportFormat:
    cleaned = (raw_value or "").strip().lower()
    if not cleaned:
        return ReportFormat.HTML
    try:
        return ReportFormat(cleaned)
    except ValueError:
        return ReportFormat.HTML


def _resolve_month_window(month_label: str | None = None) -> MonthWindow:
    if month_label:
        chunks = month_label.split("-")
        if len(chunks) != 2:
            raise ValueError("month_label must be in YYYY-MM format")
        year = int(chunks[0])
        month = int(chunks[1])
    else:
        this_month_start = date.today().replace(day=1)
        previous_month_last_day = this_month_start - timedelta(days=1)
        year = previous_month_last_day.year
        month = previous_month_last_day.month

    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    return MonthWindow(
        label=f"{year:04d}-{month:02d}",
        start_date=start_date,
        end_date=end_date,
        start_dt=datetime.combine(start_date, datetime.min.time()),
        end_dt=datetime.combine(end_date, datetime.min.time()),
    )


def _deliver_notification(
    user: User,
    channel: NotificationChannel,
    title: str,
    message: str,
) -> tuple[NotificationStatus, str]:
    if channel == NotificationChannel.IN_APP:
        return NotificationStatus.SENT, "Delivered to in-app inbox"

    if channel == NotificationChannel.EMAIL:
        smtp_host = current_app.config.get("SMTP_HOST")
        recipient = (user.email or "").strip()
        if not smtp_host or not recipient:
            return NotificationStatus.FAILED, "SMTP host or recipient email not configured"

        email_message = EmailMessage()
        email_message["Subject"] = title
        email_message["From"] = current_app.config.get("EMAIL_SENDER")
        email_message["To"] = recipient
        email_message.set_content(message)

        try:
            smtp_port = int(current_app.config.get("SMTP_PORT", 587))
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
                if current_app.config.get("SMTP_USE_TLS", True):
                    smtp.starttls()
                smtp_username = current_app.config.get("SMTP_USERNAME")
                smtp_password = current_app.config.get("SMTP_PASSWORD")
                if smtp_username and smtp_password:
                    smtp.login(smtp_username, smtp_password)
                smtp.send_message(email_message)
            return NotificationStatus.SENT, "Email sent via SMTP"
        except Exception as exc:
            return NotificationStatus.FAILED, f"Email delivery failed: {exc}"

    if channel == NotificationChannel.GCHAT:
        webhook_url = current_app.config.get("GCHAT_WEBHOOK_URL")
        if not webhook_url:
            return NotificationStatus.FAILED, "Google Chat webhook URL not configured"
        payload = json.dumps({"text": f"{title}\n{message}"}).encode("utf-8")
        request = urllib_request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                return NotificationStatus.SENT, f"GChat webhook status {response.status}"
        except URLError as exc:
            return NotificationStatus.FAILED, f"GChat delivery failed: {exc}"

    if channel == NotificationChannel.SMS:
        sms_gateway_url = current_app.config.get("SMS_GATEWAY_URL")
        recipient_number = None
        if user.student_profile and user.student_profile.contact_number:
            recipient_number = user.student_profile.contact_number
        elif user.company_profile and user.company_profile.hr_contact:
            recipient_number = user.company_profile.hr_contact
        if not sms_gateway_url:
            return NotificationStatus.FAILED, "SMS gateway URL not configured"
        if not recipient_number:
            return NotificationStatus.FAILED, "SMS recipient contact number not available"
        payload = {
            "to": recipient_number,
            "message": f"{title} - {message}",
        }
        headers = {"Content-Type": "application/json"}
        sms_token = current_app.config.get("SMS_GATEWAY_TOKEN")
        if sms_token:
            headers["Authorization"] = f"Bearer {sms_token}"
        request = urllib_request.Request(
            sms_gateway_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                return NotificationStatus.SENT, f"SMS gateway status {response.status}"
        except URLError as exc:
            return NotificationStatus.FAILED, f"SMS delivery failed: {exc}"

    return NotificationStatus.FAILED, "Unsupported notification channel"


def _create_notification(
    *,
    user: User,
    title: str,
    message: str,
    channel: NotificationChannel,
    related_job_id: int | None = None,
    metadata: dict | None = None,
) -> Notification:
    delivery_status, delivery_response = _deliver_notification(user, channel, title, message)
    effective_channel = channel

    if delivery_status == NotificationStatus.FAILED and channel != NotificationChannel.IN_APP:
        fallback_status, fallback_response = _deliver_notification(
            user,
            NotificationChannel.IN_APP,
            title,
            message,
        )
        effective_channel = NotificationChannel.IN_APP
        delivery_status = fallback_status
        delivery_response = f"{delivery_response}; fallback={fallback_response}"

    notification = Notification(
        user_id=user.id,
        channel=effective_channel,
        status=delivery_status,
        title=title,
        message=message,
        related_job_id=related_job_id,
        delivery_response=delivery_response,
        metadata_json=metadata,
    )
    db.session.add(notification)
    return notification


def _render_report_html(summary: dict) -> str:
    status_rows = "".join(
        f"<tr><td>{status}</td><td>{count}</td></tr>"
        for status, count in summary["status_breakdown"].items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Placement Report {summary["month_label"]}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    h1, h2 {{ margin-bottom: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f8fafc; }}
    .stats-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    .stat {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; }}
  </style>
</head>
<body>
  <h1>Placement Portal Monthly Report</h1>
  <p><strong>Company:</strong> {summary["company_name"]}</p>
  <p><strong>Month:</strong> {summary["month_label"]}</p>
  <div class="stats-grid">
    <div class="stat">Total job postings: {summary["total_job_postings"]}</div>
    <div class="stat">Job postings created this month: {summary["job_postings_created"]}</div>
    <div class="stat">Applications received this month: {summary["applications_received"]}</div>
    <div class="stat">Placed candidates this month: {summary["placements_finalized"]}</div>
    <div class="stat">Average offered salary: {summary["average_offer_salary"]}</div>
    <div class="stat">Report generated at: {summary["generated_at"]}</div>
  </div>
  <h2>Status Breakdown (Current Pipeline)</h2>
  <table>
    <thead>
      <tr><th>Status</th><th>Count</th></tr>
    </thead>
    <tbody>{status_rows}</tbody>
  </table>
</body>
</html>"""


def _write_report_pdf(file_path: Path, summary: dict) -> None:
    pdf = canvas.Canvas(str(file_path), pagesize=A4)
    width, height = A4
    y = height - 50
    lines = [
        "Placement Portal Monthly Report",
        f"Company: {summary['company_name']}",
        f"Month: {summary['month_label']}",
        f"Total job postings: {summary['total_job_postings']}",
        f"Job postings created this month: {summary['job_postings_created']}",
        f"Applications received this month: {summary['applications_received']}",
        f"Placed candidates this month: {summary['placements_finalized']}",
        f"Average offered salary: {summary['average_offer_salary']}",
        f"Generated at: {summary['generated_at']}",
        "",
        "Status Breakdown",
    ]
    for status, count in summary["status_breakdown"].items():
        lines.append(f"- {status}: {count}")

    for line in lines:
        if y < 40:
            pdf.showPage()
            y = height - 50
        pdf.drawString(40, y, line)
        y -= 16
    pdf.save()


def _company_report_summary(company: Company, window: MonthWindow) -> dict:
    applications_for_company = Application.query.join(JobPosition).filter(
        JobPosition.company_id == company.id
    )
    applications_received = applications_for_company.filter(
        and_(Application.applied_at >= window.start_dt, Application.applied_at < window.end_dt)
    ).count()
    status_breakdown = {
        "applied": applications_for_company.filter(
            Application.status == ApplicationStatus.APPLIED
        ).count(),
        "shortlisted": applications_for_company.filter(
            Application.status == ApplicationStatus.SHORTLISTED
        ).count(),
        "interview": applications_for_company.filter(
            Application.status == ApplicationStatus.INTERVIEW
        ).count(),
        "offer": applications_for_company.filter(
            Application.status.in_([ApplicationStatus.OFFER, ApplicationStatus.SELECTED])
        ).count(),
        "rejected": applications_for_company.filter(
            Application.status == ApplicationStatus.REJECTED
        ).count(),
        "placed": applications_for_company.filter(
            Application.status == ApplicationStatus.PLACED
        ).count(),
    }

    placements_this_month = Placement.query.filter(
        Placement.company_id == company.id,
        Placement.created_at >= window.start_dt,
        Placement.created_at < window.end_dt,
    ).all()
    salaries = [float(placement.salary) for placement in placements_this_month if placement.salary]
    average_salary = round(sum(salaries) / len(salaries), 2) if salaries else 0

    return {
        "company_id": company.id,
        "company_name": company.company_name,
        "month_label": window.label,
        "total_job_postings": JobPosition.query.filter_by(company_id=company.id).count(),
        "job_postings_created": JobPosition.query.filter(
            JobPosition.company_id == company.id,
            JobPosition.created_at >= window.start_dt,
            JobPosition.created_at < window.end_dt,
        ).count(),
        "applications_received": applications_received,
        "placements_finalized": len(placements_this_month),
        "average_offer_salary": average_salary,
        "status_breakdown": status_breakdown,
        "generated_at": _utcnow().isoformat(),
    }


def _export_student_rows(user: User) -> tuple[list[str], list[dict]]:
    student = user.student_profile
    if not student:
        raise ValueError("Student profile not found for export requester")

    applications = (
        Application.query.join(JobPosition, Application.job_id == JobPosition.id)
        .join(Company, JobPosition.company_id == Company.id)
        .filter(Application.student_id == student.id)
        .order_by(Application.applied_at.desc())
        .all()
    )
    rows: list[dict] = []
    for application in applications:
        latest_interview = (
            max(application.interviews, key=lambda interview: interview.scheduled_at)
            if application.interviews
            else None
        )
        placement = application.placement
        rows.append(
            {
                "student_id": student.id,
                "student_name": student.full_name,
                "company_name": application.job_position.company.company_name
                if application.job_position and application.job_position.company
                else None,
                "job_id": application.job_id,
                "job_title": application.job_position.title if application.job_position else None,
                "application_status": application.status.value,
                "applied_at": application.applied_at.isoformat(),
                "updated_at": application.updated_at.isoformat(),
                "latest_interview_at": (
                    latest_interview.scheduled_at.isoformat() if latest_interview else None
                ),
                "placement_status": "placed" if placement else "pending",
                "placement_id": placement.id if placement else None,
                "position_title": placement.position_title if placement else None,
                "joining_date": placement.joining_date.isoformat() if placement else None,
                "salary": float(placement.salary) if placement and placement.salary else None,
            }
        )

    fieldnames = [
        "student_id",
        "student_name",
        "company_name",
        "job_id",
        "job_title",
        "application_status",
        "applied_at",
        "updated_at",
        "latest_interview_at",
        "placement_status",
        "placement_id",
        "position_title",
        "joining_date",
        "salary",
    ]
    return fieldnames, rows


def _export_company_rows(user: User) -> tuple[list[str], list[dict]]:
    company = user.company_profile
    if not company:
        raise ValueError("Company profile not found for export requester")

    applications = (
        Application.query.join(Student, Application.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .join(JobPosition, Application.job_id == JobPosition.id)
        .filter(JobPosition.company_id == company.id)
        .order_by(Application.applied_at.desc())
        .all()
    )
    rows: list[dict] = []
    for application in applications:
        student = application.student
        latest_interview = (
            max(application.interviews, key=lambda interview: interview.scheduled_at)
            if application.interviews
            else None
        )
        placement = application.placement
        rows.append(
            {
                "company_id": company.id,
                "company_name": company.company_name,
                "job_id": application.job_id,
                "job_title": application.job_position.title if application.job_position else None,
                "student_id": student.id if student else None,
                "student_name": student.full_name if student else None,
                "student_email": student.user.email if student and student.user else None,
                "student_branch": student.branch if student else None,
                "application_status": application.status.value,
                "applied_at": application.applied_at.isoformat(),
                "updated_at": application.updated_at.isoformat(),
                "latest_interview_at": (
                    latest_interview.scheduled_at.isoformat() if latest_interview else None
                ),
                "placement_status": "placed" if placement else "pending",
                "placement_id": placement.id if placement else None,
                "joining_date": placement.joining_date.isoformat() if placement else None,
                "salary": float(placement.salary) if placement and placement.salary else None,
            }
        )

    fieldnames = [
        "company_id",
        "company_name",
        "job_id",
        "job_title",
        "student_id",
        "student_name",
        "student_email",
        "student_branch",
        "application_status",
        "applied_at",
        "updated_at",
        "latest_interview_at",
        "placement_status",
        "placement_id",
        "joining_date",
        "salary",
    ]
    return fieldnames, rows


@celery.task(name="app.tasks.send_interview_reminders_task")
def send_interview_reminders_task():
    now = _utcnow()
    lookahead_hours = int(current_app.config.get("REMINDER_LOOKAHEAD_HOURS", 24))
    upper_bound = now + timedelta(hours=lookahead_hours)
    configured_channel = _normalize_notification_channel(
        current_app.config.get("DEFAULT_NOTIFICATION_CHANNEL")
    )

    interviews = (
        Interview.query.join(Application, Interview.application_id == Application.id)
        .join(Student, Application.student_id == Student.id)
        .join(User, Student.user_id == User.id)
        .join(JobPosition, Application.job_id == JobPosition.id)
        .join(Company, JobPosition.company_id == Company.id)
        .filter(
            Interview.status == InterviewStatus.SCHEDULED,
            Interview.scheduled_at >= now,
            Interview.scheduled_at <= upper_bound,
            Student.is_active.is_(True),
            User.is_active.is_(True),
            User.is_blacklisted.is_(False),
            Company.is_active.is_(True),
            Company.approval_status == CompanyApprovalStatus.APPROVED,
            JobPosition.status == DriveStatus.APPROVED,
        )
        .order_by(Interview.scheduled_at.asc())
        .all()
    )

    reminders_sent = 0
    skipped = 0
    for interview in interviews:
        if interview.last_reminder_sent_at and interview.last_reminder_sent_at.date() == now.date():
            skipped += 1
            continue

        application = interview.application
        student = application.student if application else None
        student_user = student.user if student else None
        company = interview.company
        job_title = application.job_position.title if application and application.job_position else "Job"
        if not student_user:
            skipped += 1
            continue

        message = (
            f"Reminder: Your interview for '{job_title}' with "
            f"'{company.company_name if company else 'Company'}' is scheduled at "
            f"{interview.scheduled_at.isoformat()}."
        )
        _create_notification(
            user=student_user,
            channel=configured_channel,
            title="Interview Reminder",
            message=message,
            metadata={
                "type": "interview_reminder",
                "interview_id": interview.id,
                "application_id": interview.application_id,
            },
        )
        interview.last_reminder_sent_at = now
        reminders_sent += 1

    db.session.commit()
    return {
        "evaluated": len(interviews),
        "sent": reminders_sent,
        "skipped": skipped,
        "window_hours": lookahead_hours,
    }


@celery.task(name="app.tasks.generate_monthly_reports_task", bind=True)
def generate_monthly_reports_task(
    self,
    month_label: str | None = None,
    report_format: str | None = None,
):
    window = _resolve_month_window(month_label)
    report_type = _normalize_report_format(
        report_format or current_app.config.get("MONTHLY_REPORT_FORMAT")
    )
    report_root = Path(current_app.config["JOB_REPORT_DIR"]).resolve()
    report_root.mkdir(parents=True, exist_ok=True)

    companies = (
        Company.query.join(User, Company.user_id == User.id)
        .filter(
            Company.approval_status == CompanyApprovalStatus.APPROVED,
            Company.is_active.is_(True),
            User.is_active.is_(True),
            User.is_blacklisted.is_(False),
        )
        .order_by(Company.company_name.asc())
        .all()
    )

    generated = 0
    failed: list[dict] = []
    for company in companies:
        try:
            summary = _company_report_summary(company, window)
            company_dir = report_root / f"company_{company.id}"
            company_dir.mkdir(parents=True, exist_ok=True)
            extension = "html" if report_type == ReportFormat.HTML else "pdf"
            file_name = f"placement_report_{window.label}.{extension}"
            file_path = company_dir / file_name

            if report_type == ReportFormat.HTML:
                file_path.write_text(_render_report_html(summary), encoding="utf-8")
            else:
                _write_report_pdf(file_path, summary)

            report_record = PlacementReport.query.filter_by(
                company_id=company.id,
                month_label=window.label,
                report_format=report_type,
            ).first()
            if report_record is None:
                report_record = PlacementReport(
                    company_id=company.id,
                    month_label=window.label,
                    report_format=report_type,
                    file_name=file_name,
                    file_path=str(file_path),
                    summary_json=summary,
                    generated_at=_utcnow(),
                    celery_task_id=self.request.id,
                )
                db.session.add(report_record)
            else:
                report_record.file_name = file_name
                report_record.file_path = str(file_path)
                report_record.summary_json = summary
                report_record.generated_at = _utcnow()
                report_record.celery_task_id = self.request.id

            if company.user:
                db.session.flush()
                _create_notification(
                    user=company.user,
                    channel=NotificationChannel.IN_APP,
                    title=f"Monthly placement report ready ({window.label})",
                    message=(
                        f"Your {report_type.value.upper()} report for {window.label} is available "
                        f"for download."
                    ),
                    metadata={
                        "type": "monthly_report",
                        "report_id": report_record.id,
                        "month_label": window.label,
                        "format": report_type.value,
                    },
                )
            db.session.commit()
            generated += 1
        except Exception as exc:
            db.session.rollback()
            failed.append({"company_id": company.id, "error": str(exc)})

    return {
        "month_label": window.label,
        "format": report_type.value,
        "generated": generated,
        "failed": failed,
    }


@celery.task(name="app.tasks.process_export_job_task", bind=True)
def process_export_job_task(self, export_job_id: int):
    export_job = db.session.get(AsyncExportJob, export_job_id)
    if not export_job:
        raise ValueError(f"AsyncExportJob id={export_job_id} does not exist")

    export_job.status = AsyncJobStatus.RUNNING
    export_job.started_at = _utcnow()
    export_job.celery_task_id = self.request.id
    db.session.commit()

    try:
        requester = export_job.requester_user
        if requester is None:
            raise ValueError("Export job requester not found")

        if export_job.scope == ExportScope.STUDENT_HISTORY:
            fieldnames, rows = _export_student_rows(requester)
        elif export_job.scope == ExportScope.COMPANY_HISTORY:
            fieldnames, rows = _export_company_rows(requester)
        else:
            raise ValueError("Unsupported export scope")

        export_root = Path(current_app.config["JOB_EXPORT_DIR"]).resolve()
        destination_dir = export_root / f"user_{requester.id}"
        destination_dir.mkdir(parents=True, exist_ok=True)

        timestamp = _utcnow().strftime("%Y%m%d%H%M%S")
        file_name = f"{export_job.scope.value}_{export_job.id}_{timestamp}.csv"
        file_path = destination_dir / file_name
        with file_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        export_job.status = AsyncJobStatus.COMPLETED
        export_job.file_name = file_name
        export_job.file_path = str(file_path)
        export_job.row_count = len(rows)
        export_job.error_message = None
        export_job.metadata_json = {
            "columns": fieldnames,
            "generated_at": _utcnow().isoformat(),
        }
        export_job.completed_at = _utcnow()

        _create_notification(
            user=requester,
            channel=NotificationChannel.IN_APP,
            title="CSV export completed",
            message=(
                f"Your {export_job.scope.value.replace('_', ' ')} export is ready "
                f"with {len(rows)} records."
            ),
            related_job_id=export_job.id,
            metadata={
                "type": "csv_export",
                "export_job_id": export_job.id,
                "scope": export_job.scope.value,
                "rows": len(rows),
            },
        )
        db.session.commit()
        return {
            "export_job_id": export_job.id,
            "status": export_job.status.value,
            "row_count": export_job.row_count,
            "file_name": export_job.file_name,
        }
    except Exception as exc:
        db.session.rollback()
        failed_job = db.session.get(AsyncExportJob, export_job_id)
        if failed_job:
            failed_job.status = AsyncJobStatus.FAILED
            failed_job.error_message = str(exc)
            failed_job.completed_at = _utcnow()
            requester = failed_job.requester_user
            if requester:
                _create_notification(
                    user=requester,
                    channel=NotificationChannel.IN_APP,
                    title="CSV export failed",
                    message=(
                        f"Your {failed_job.scope.value.replace('_', ' ')} export could not be "
                        f"generated. Error: {exc}"
                    ),
                    related_job_id=failed_job.id,
                    metadata={
                        "type": "csv_export_failed",
                        "export_job_id": failed_job.id,
                        "scope": failed_job.scope.value,
                    },
                )
            db.session.commit()
        raise
