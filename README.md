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

## Database Models
- `User` (roles: `admin`, `company`, `student`)
- `Company` (profile + approval status)
- `Student` (profile + education + skills + resume)
- `JobPosition` (drive/job details created by company)
- `Application` (student application to a job/drive)
- `Interview` (company interview scheduling for shortlisted candidates)
- `Placement` (final placement record)

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
- Redis (cache + Celery broker/back-end; to be integrated in upcoming milestones)
- Vue.js + Bootstrap (UI in upcoming milestones)

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
5. Open:
   ```
   http://127.0.0.1:5000/
   ```

## Default Admin Seed (Override via env vars)
- `PPA_ADMIN_EMAIL` (default: `admin@institute.edu`)
- `PPA_ADMIN_PASSWORD` (default: `admin123`)
- `PPA_RESET_DB=1` (optional, drops and recreates all tables before seeding)

## Auth + RBAC Rules
- Admin: predefined user only (no registration endpoint).
- Student: self-registration + login.
- Company: registration allowed, login allowed only after admin approval (`approved` status).
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
- `PATCH /api/company/applications/<application_id>/status`
- `POST /api/company/applications/<application_id>/interviews`
- `GET /api/company/interviews`
- `PATCH /api/company/interviews/<interview_id>/status`
- `GET /api/student/overview`
- `PATCH /api/student/profile`
- `GET /api/student/jobs`
- `POST /api/student/jobs/<job_id>/apply`
- `GET /api/student/applications`
- `GET /api/student/interviews`
- `GET /api/student/applications/<application_id>/offer-letter`
- `GET /api/student/applications/<application_id>/placement-confirmation`
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
