"""
SQLite-backed job queue for notification tasks with retry/backoff support.

MVP queue implementation - lightweight, no external dependencies.
"""
import os
import time
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.models import NotificationTask, Alert


# Config
DEFAULT_MAX_ATTEMPTS = int(os.getenv('QUEUE_MAX_ATTEMPTS', '3'))
BASE_BACKOFF_SECONDS = int(os.getenv('QUEUE_BASE_BACKOFF_SECONDS', '60'))
MAX_BACKOFF_SECONDS = int(os.getenv('QUEUE_MAX_BACKOFF_SECONDS', '3600'))


def compute_backoff(attempts: int) -> int:
    """Exponential backoff with jitter, capped at MAX_BACKOFF_SECONDS."""
    import random
    backoff = min(BASE_BACKOFF_SECONDS * (2 ** attempts), MAX_BACKOFF_SECONDS)
    jitter = random.uniform(0, backoff * 0.1)
    return int(backoff + jitter)


def enqueue_notification(
    db: Session,
    alert_id: int,
    channel: str,
    target: str,
    message: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> NotificationTask:
    """Add a notification task to the queue."""
    task = NotificationTask(
        alert_id=alert_id,
        channel=channel,
        target=target,
        message=message,
        status='pending',
        attempts=0,
        max_attempts=max_attempts,
        next_retry_at=datetime.utcnow(),
    )
    db.add(task)
    db.flush()
    return task


def fetch_pending_tasks(db: Session, limit: int = 10) -> List[NotificationTask]:
    """Fetch tasks ready for processing (pending or retry-ready)."""
    now = datetime.utcnow()
    stmt = (
        select(NotificationTask)
        .where(
            NotificationTask.status.in_(['pending', 'failed']),
            NotificationTask.attempts < NotificationTask.max_attempts,
            (NotificationTask.next_retry_at == None) | (NotificationTask.next_retry_at <= now),
        )
        .order_by(NotificationTask.next_retry_at.asc().nullsfirst())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def mark_task_processing(db: Session, task_id: int) -> bool:
    """Mark task as processing. Returns False if already taken."""
    stmt = (
        update(NotificationTask)
        .where(
            NotificationTask.id == task_id,
            NotificationTask.status.in_(['pending', 'failed']),
        )
        .values(status='processing', updated_at=datetime.utcnow())
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount > 0


def mark_task_completed(db: Session, task_id: int) -> None:
    """Mark task as successfully completed."""
    task = db.get(NotificationTask, task_id)
    if task:
        task.status = 'completed'
        task.attempts += 1
        task.updated_at = datetime.utcnow()
        # Update corresponding alert status
        alert = db.get(Alert, task.alert_id)
        if alert:
            alert.status = 'sent'
        db.commit()


def mark_task_failed(db: Session, task_id: int, error: str) -> None:
    """Mark task as failed, schedule retry if attempts remain."""
    task = db.get(NotificationTask, task_id)
    if task:
        task.attempts += 1
        task.last_error = error
        task.updated_at = datetime.utcnow()

        if task.attempts >= task.max_attempts:
            task.status = 'failed'
            # Update corresponding alert status
            alert = db.get(Alert, task.alert_id)
            if alert:
                alert.status = 'failed'
        else:
            task.status = 'failed'  # Will be retried
            backoff = compute_backoff(task.attempts)
            task.next_retry_at = datetime.utcnow() + timedelta(seconds=backoff)

        db.commit()


def get_queue_stats(db: Session) -> dict:
    """Get queue statistics for dashboard."""
    from sqlalchemy import func

    stats = {}
    for status in ['pending', 'processing', 'completed', 'failed']:
        count = db.scalar(
            select(func.count(NotificationTask.id))
            .where(NotificationTask.status == status)
        )
        stats[status] = count or 0

    # Failed with retries remaining
    stats['retry_pending'] = db.scalar(
        select(func.count(NotificationTask.id))
        .where(
            NotificationTask.status == 'failed',
            NotificationTask.attempts < NotificationTask.max_attempts,
        )
    ) or 0

    return stats
