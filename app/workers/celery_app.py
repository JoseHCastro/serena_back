"""
Celery application factory and configuration.

Defines the Celery app used for background tasks such as
post-session emotional video analysis.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "serena_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.modules.biometric.tasks",  # Register biometric task module
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task behavior
    task_acks_late=True,          # Acknowledge after task completes (safer)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1, # One task at a time per worker process
    # Result expiration: 24 hours
    result_expires=86400,
    # Retry policy defaults
    task_max_retries=3,
    task_default_retry_delay=60,  # seconds
)

# Import all ORM models to ensure SQLAlchemy registers all mappers and relationships
# before any background task runs. This prevents Missing/Uninitialized mapper errors.
import app.modules.auth.models  # noqa
import app.modules.users.models  # noqa
import app.modules.patients.models  # noqa
import app.modules.sessions.models  # noqa
import app.modules.biometric.models  # noqa
import app.modules.alerts.models  # noqa
