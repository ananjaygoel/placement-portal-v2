from __future__ import annotations

from app import create_app
from app.extensions import celery

flask_app = create_app()

import app.tasks  # noqa: E402,F401

__all__ = ("celery",)
