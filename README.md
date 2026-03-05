# Placement Portal Application (PPA) - V2

Placement Portal Application (PPA) is an academic project to manage institute placement activities for three roles: **Admin**, **Company**, and **Student**.

This repository currently includes:
- Flask backend scaffold
- SQLite database models and relationships
- Programmatic database initialization
- Automatic pre-creation of the Admin user
- JWT authentication and role-based dashboard APIs
- Vue + Bootstrap authentication UI (served by Flask)
- Admin management APIs for companies, students, drives, and applications
- Company dashboard and job/application/interview management APIs
- Student dashboard with profile, job search/apply, tracking, and document download
- Placement tracking with full status history and placement timeline
- Celery + Redis background jobs for reminders, monthly reports, and async CSV exports

## Database Models
- `User` (roles: `admin`, `company`, `student`)
- `Company` (profile + approval status)
- `Student` (profile + education + skills + resume)
- `JobPosition` (drive/job details created by company)
- `Application` (student application to a job/drive)
- `ApplicationStatusHistory` (audit trail of every status transition)
- `Interview` (company interview scheduling for shortlisted candidates)
- `Placement` (final placement record)
- `AsyncExportJob` (track async CSV export queue/status/files)
- `PlacementReport` (monthly HTML/PDF company report records)
- `Notification` (in-app/email/gchat/sms delivery records)

## Key Relationships
- `User` 1:1 `Company`
- `User` 1:1 `Student`
- `Company` 1:N `JobPosition`
- `Student` 1:N `Application`
- `JobPosition` 1:N `Application`
- `Application` 1:1 `Placement` (optional until finalized)
- `Student` 1:N `Placement`
- `Company` 1:N `Placement`

## Tech Stack
- Flask (API)
- SQLite (database)
- Redis (Celery broker/result backend + API caching)
- Celery + Celery Beat (scheduled + async jobs)
- Vue.js + Bootstrap (single-page dashboard UI)

## Quick Start (Backend)
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Initialize database and seed admin:
   ```bash
   python scripts/init_db.py
   ```
4. Run Flask app:
   ```bash
   python run.py
   ```
5. Start Redis (new terminal):
   ```bash
   redis-server
   ```
6. Run Celery worker (new terminal):
   ```bash
   celery -A app.celery_worker.celery worker --loglevel=info
   ```
7. Run Celery Beat scheduler (new terminal):
   ```bash
   celery -A app.celery_worker.celery beat --loglevel=info
   ```
8. Open:
   ```
   http://127.0.0.1:5000/
   ```

## Default Admin Seed (Override via env vars)
- `PPA_ADMIN_EMAIL` (default: `admin@institute.edu`)
- `PPA_ADMIN_PASSWORD` (default: `admin123`)
- `PPA_RESET_DB=1` (optional, drops and recreates all tables before seeding)
- `CELERY_BROKER_URL` (default: `redis://localhost:6379/0`)
- `CELERY_RESULT_BACKEND` (default: same as broker)
- `REDIS_CACHE_URL` (default: `redis://localhost:6379/1`)
- `CACHE_ENABLED` (`1` or `0`)
- `CACHE_JOB_LIST_TTL_SECONDS` (default: `90`)
- `CACHE_COMPANY_SEARCH_TTL_SECONDS` (default: `180`)
- `CACHE_STUDENT_SEARCH_TTL_SECONDS` (default: `180`)
- `DEADLINE_REMINDER_LOOKAHEAD_DAYS` (default: `3`)
- `DEFAULT_NOTIFICATION_CHANNEL` (`in_app` / `email` / `gchat` / `sms`)
- `MONTHLY_REPORT_FORMAT` (`html` or `pdf`)

## Scheduled + Async Jobs
- Daily application deadline reminder job (`send_application_deadline_reminders_task`) via Celery Beat.
- Monthly institute activity report job (`generate_monthly_reports_task`) via Celery Beat.
  - Generates institute-level report for Admin (drives conducted, students applied/selected/placed).
  - Sends report to Admin via email (falls back to in-app notification if email delivery fails).
  - Also continues generating company-level monthly report files for company dashboards.
- User-triggered async CSV exports (`process_export_job_task`) for:
  - Student application and placement history.
  - Company application and placement pipeline history.
- In-app notification records are generated for reminders, report availability, and export completion/failure.

## Redis API Caching
- Read-through Redis cache is enabled for:
  - `GET /api/student/jobs` (job listing + filters)
  - `GET /api/admin/companies` (company search)
  - `GET /api/admin/students` (student search)
- Cache expiry policy:
  - Job listing TTL: `CACHE_JOB_LIST_TTL_SECONDS`
  - Company search TTL: `CACHE_COMPANY_SEARCH_TTL_SECONDS`
  - Student search TTL: `CACHE_STUDENT_SEARCH_TTL_SECONDS`
- Cache refresh policy:
  - Expired keys are lazily rebuilt on next request.
  - API responses include `X-Cache: HIT` or `X-Cache: MISS`.
- Cache invalidation policy:
  - Company writes invalidate company-search and student-job cache keys.
  - Student writes invalidate student-search and student-job cache keys.
  - Drive/application writes invalidate student-job cache keys.

## Auth + RBAC Rules
- Admin: predefined user only (no registration endpoint).
- Student: self-registration + login.
- Company: registration allowed, login allowed only after admin approval (`approved` status).
- Application status workflow: `applied -> shortlisted -> interview -> offer -> placed` (or `rejected`).
- On login, UI redirects to role-specific dashboards:
  - `#admin-dashboard`
  - `#company-dashboard`
  - `#student-dashboard`

## Main API Endpoints
- `POST /api/auth/register/student`
- `POST /api/auth/register/company`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/admin/overview`
- `GET /api/admin/companies`
- `PATCH /api/admin/companies/<company_id>/approval`
- `PATCH /api/admin/companies/<company_id>/status`
- `DELETE /api/admin/companies/<company_id>`
- `GET /api/admin/students`
- `GET /api/admin/students/<student_id>`
- `PATCH /api/admin/students/<student_id>/status`
- `DELETE /api/admin/students/<student_id>`
- `GET /api/admin/drives`
- `PATCH /api/admin/drives/<drive_id>/status`
- `DELETE /api/admin/drives/<drive_id>`
- `GET /api/admin/applications`
- `PATCH /api/admin/applications/<application_id>/status`
- `DELETE /api/admin/applications/<application_id>`
- `GET /api/company/overview`
- `POST /api/company/jobs`
- `GET /api/company/jobs`
- `PATCH /api/company/jobs/<job_id>/status`
- `GET /api/company/jobs/<job_id>/applications`
- `GET /api/company/applications`
- `GET /api/company/students/<student_id>`
- `PATCH /api/company/applications/<application_id>/status`
- `POST /api/company/applications/<application_id>/interviews`
- `GET /api/company/interviews`
- `PATCH /api/company/interviews/<interview_id>/status`
- `POST /api/company/exports`
- `GET /api/company/exports`
- `GET /api/company/exports/<export_job_id>/download`
- `GET /api/company/reports`
- `GET /api/company/reports/<report_id>/download`
- `GET /api/company/notifications`
- `PATCH /api/company/notifications/<notification_id>/read`
- `GET /api/student/overview`
- `PATCH /api/student/profile`
- `GET /api/student/jobs`
- `POST /api/student/jobs/<job_id>/apply`
- `GET /api/student/applications`
- `GET /api/student/interviews`
- `POST /api/student/exports`
- `GET /api/student/exports`
- `GET /api/student/exports/<export_job_id>/download`
- `GET /api/student/notifications`
- `PATCH /api/student/notifications/<notification_id>/read`
- `GET /api/student/applications/<application_id>/offer-letter`
- `GET /api/student/applications/<application_id>/placement-confirmation`
- `GET /api/admin/exports`
- `GET /api/admin/reports`
- `GET /api/dashboard/admin`
- `GET /api/dashboard/company`
- `GET /api/dashboard/student`

## Milestone Status
- Milestone 0: Repository setup ✅
- Milestone 1: DB models and schema setup ✅
- Milestone 2: Authentication + RBAC ✅
- Milestone 3: Admin dashboard and management ✅
- Milestone 4: Company dashboard and job/application management ✅
- Milestone 5: Student dashboard and job application system ✅
- Milestone 6: Job application history and status tracking ✅
- Milestone 7: Backend jobs with Celery + Redis ✅
- Milestone 8: Redis caching and API optimization ✅
