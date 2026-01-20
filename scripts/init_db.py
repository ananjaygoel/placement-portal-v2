from __future__ import annotations

import os
from pathlib import Path
import sys

from werkzeug.security import generate_password_hash

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import User, UserRole


def seed_admin() -> None:
    admin_email = os.getenv("PPA_ADMIN_EMAIL", "admin@institute.edu").strip().lower()
    admin_password = os.getenv("PPA_ADMIN_PASSWORD", "admin123")

    existing_admin = User.query.filter_by(role=UserRole.ADMIN).first()
    if existing_admin:
        print(f"Admin already exists: {existing_admin.email}")
        return

    email_in_use = User.query.filter_by(email=admin_email).first()
    if email_in_use:
        raise ValueError(
            f"Cannot seed admin. Email '{admin_email}' already belongs to role '{email_in_use.role.value}'."
        )

    admin = User(
        email=admin_email,
        password_hash=generate_password_hash(admin_password),
        role=UserRole.ADMIN,
        is_active=True,
        is_blacklisted=False,
    )
    db.session.add(admin)
    db.session.commit()
    print(f"Seeded admin user: {admin.email}")


def main() -> None:
    app = create_app()

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    with app.app_context():
        db.create_all()
        seed_admin()
        print("Database initialization complete.")


if __name__ == "__main__":
    main()
