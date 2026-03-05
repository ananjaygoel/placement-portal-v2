from __future__ import annotations

from celery import Celery
from flask_sqlalchemy import SQLAlchemy
from redis import Redis

db = SQLAlchemy()
celery = Celery(__name__)
redis_client: Redis | None = None


def init_celery(app):
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        timezone=app.config["CELERY_TIMEZONE"],
        beat_schedule=app.config["CELERY_BEAT_SCHEDULE"],
        task_track_started=app.config["CELERY_TASK_TRACK_STARTED"],
        task_time_limit=app.config["CELERY_TASK_TIME_LIMIT"],
        task_soft_time_limit=app.config["CELERY_TASK_SOFT_TIME_LIMIT"],
        worker_hijack_root_logger=False,
    )

    class FlaskContextTask(celery.Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = FlaskContextTask
    return celery


def init_redis(app):
    global redis_client

    if not app.config.get("CACHE_ENABLED", True):
        redis_client = None
        return redis_client

    try:
        redis_client = Redis.from_url(
            app.config["REDIS_CACHE_URL"],
            decode_responses=True,
        )
        if app.config.get("CACHE_PING_ON_STARTUP", False):
            redis_client.ping()
    except Exception as exc:
        app.logger.warning("Redis cache disabled: %s", exc)
        redis_client = None
    return redis_client


def get_redis_client() -> Redis | None:
    return redis_client
