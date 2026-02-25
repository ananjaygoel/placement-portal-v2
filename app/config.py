from __future__ import annotations

import os
from pathlib import Path

from celery.schedules import crontab


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'ppa.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
    CELERY_TIMEZONE = os.getenv("CELERY_TIMEZONE", "Asia/Kolkata")
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "900"))
    CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "840"))
    CELERY_BEAT_SCHEDULE = {
        "daily-interview-reminders": {
            "task": "app.tasks.send_interview_reminders_task",
            "schedule": crontab(hour=9, minute=0),
        },
        "monthly-placement-reports": {
            "task": "app.tasks.generate_monthly_reports_task",
            "schedule": crontab(day_of_month=1, hour=7, minute=0),
        },
    }

    JOB_EXPORT_DIR = str(BASE_DIR / "instance" / "exports")
    JOB_REPORT_DIR = str(BASE_DIR / "instance" / "reports")
    DEFAULT_NOTIFICATION_CHANNEL = os.getenv("DEFAULT_NOTIFICATION_CHANNEL", "in_app")
    REMINDER_LOOKAHEAD_HOURS = int(os.getenv("REMINDER_LOOKAHEAD_HOURS", "24"))
    MONTHLY_REPORT_FORMAT = os.getenv("MONTHLY_REPORT_FORMAT", "html")
    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "placements@institute.edu")
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1") == "1"
    GCHAT_WEBHOOK_URL = os.getenv("GCHAT_WEBHOOK_URL")
    SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL")
    SMS_GATEWAY_TOKEN = os.getenv("SMS_GATEWAY_TOKEN")
