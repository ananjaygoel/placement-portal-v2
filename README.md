# Placement Portal Application (PPA) - V2

Placement Portal Application (PPA) is an academic project to manage institute placement activities for three roles: **Admin**, **Company**, and **Student**.

This repository currently includes:
- Flask backend scaffold
- SQLite database models and relationships
- Programmatic database initialization
- Automatic pre-creation of the Admin user

## Database Models
- `User` (roles: `admin`, `company`, `student`)
- `Company` (profile + approval status)
- `Student` (profile + education + skills + resume)
- `JobPosition` (drive/job details created by company)
- `Application` (student application to a job/drive)
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

## Default Admin Seed (Override via env vars)
- `PPA_ADMIN_EMAIL` (default: `admin@institute.edu`)
- `PPA_ADMIN_PASSWORD` (default: `admin123`)
- `PPA_ADMIN_FULL_NAME` (default: `Placement Admin`)

## Milestone Status
- Milestone 0: Repository setup ✅
- Milestone 1 (in progress): DB models and schema setup
