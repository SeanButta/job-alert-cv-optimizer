"""Tests for notification queue and retry behavior."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.models import NotificationTask, Alert, User, Match, JobPost
from app.services.queue import (
    compute_backoff,
    enqueue_notification,
    fetch_pending_tasks,
    mark_task_processing,
    mark_task_completed,
    mark_task_failed,
    get_queue_stats,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def setup_alert(db_session):
    """Create prerequisite user, job, match, and alert."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.flush()

    job = JobPost(
        source="test", external_id="j1",
        title="Dev", company="Co", description="desc", link="http://x.com",
    )
    db_session.add(job)
    db_session.flush()

    match = Match(user_id=user.id, job_post_id=job.id, score=0.8, explanation="test")
    db_session.add(match)
    db_session.flush()

    alert = Alert(user_id=user.id, match_id=match.id, channel="email", status="queued")
    db_session.add(alert)
    db_session.commit()

    return alert


class TestBackoff:
    def test_first_retry_base_backoff(self):
        backoff = compute_backoff(0)
        # Base is 60 seconds + up to 10% jitter
        assert 60 <= backoff <= 66

    def test_exponential_growth(self):
        b0 = compute_backoff(0)
        b1 = compute_backoff(1)
        b2 = compute_backoff(2)
        # Should roughly double each time (accounting for jitter)
        assert b1 > b0
        assert b2 > b1

    def test_max_cap(self):
        # High attempt count should cap at max
        backoff = compute_backoff(20)
        # Default max is 3600 + jitter
        assert backoff <= 3960  # 3600 + 10%


class TestEnqueue:
    def test_enqueue_creates_task(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(
            db_session, alert.id, "email", "test@example.com", "Test message"
        )
        db_session.commit()

        assert task.id is not None
        assert task.alert_id == alert.id
        assert task.channel == "email"
        assert task.target == "test@example.com"
        assert task.message == "Test message"
        assert task.status == "pending"
        assert task.attempts == 0
        assert task.max_attempts == 3

    def test_enqueue_custom_max_attempts(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(
            db_session, alert.id, "email", "test@example.com", "Test message",
            max_attempts=5,
        )
        db_session.commit()

        assert task.max_attempts == 5


class TestFetchPending:
    def test_fetch_pending_tasks(self, db_session, setup_alert):
        alert = setup_alert
        enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg 1")
        enqueue_notification(db_session, alert.id, "sms", "+1234567890", "Msg 2")
        db_session.commit()

        tasks = fetch_pending_tasks(db_session, limit=10)
        assert len(tasks) == 2

    def test_respects_limit(self, db_session, setup_alert):
        alert = setup_alert
        for i in range(5):
            enqueue_notification(db_session, alert.id, "email", f"test{i}@example.com", f"Msg {i}")
        db_session.commit()

        tasks = fetch_pending_tasks(db_session, limit=2)
        assert len(tasks) == 2

    def test_excludes_completed(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg")
        db_session.commit()

        mark_task_processing(db_session, task.id)
        mark_task_completed(db_session, task.id)

        tasks = fetch_pending_tasks(db_session, limit=10)
        assert len(tasks) == 0

    def test_excludes_max_attempts_reached(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(
            db_session, alert.id, "email", "test@example.com", "Msg",
            max_attempts=2,
        )
        db_session.commit()

        # Fail twice
        mark_task_processing(db_session, task.id)
        mark_task_failed(db_session, task.id, "Error 1")
        task = db_session.get(NotificationTask, task.id)
        task.next_retry_at = datetime.utcnow() - timedelta(minutes=5)  # Make retry-ready
        db_session.commit()

        mark_task_processing(db_session, task.id)
        mark_task_failed(db_session, task.id, "Error 2")

        # Should not be fetched anymore
        tasks = fetch_pending_tasks(db_session, limit=10)
        assert len(tasks) == 0

    def test_respects_next_retry_at(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg")
        task.next_retry_at = datetime.utcnow() + timedelta(hours=1)
        db_session.commit()

        tasks = fetch_pending_tasks(db_session, limit=10)
        assert len(tasks) == 0


class TestTaskProcessing:
    def test_mark_processing(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg")
        db_session.commit()

        success = mark_task_processing(db_session, task.id)
        assert success is True

        task = db_session.get(NotificationTask, task.id)
        assert task.status == "processing"

    def test_mark_processing_already_taken(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg")
        db_session.commit()

        mark_task_processing(db_session, task.id)
        # Second attempt should fail
        success = mark_task_processing(db_session, task.id)
        assert success is False


class TestTaskCompletion:
    def test_mark_completed(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(db_session, alert.id, "email", "test@example.com", "Msg")
        db_session.commit()

        mark_task_processing(db_session, task.id)
        mark_task_completed(db_session, task.id)

        task = db_session.get(NotificationTask, task.id)
        assert task.status == "completed"
        assert task.attempts == 1

        # Alert should also be updated
        alert = db_session.get(Alert, alert.id)
        assert alert.status == "sent"


class TestTaskFailure:
    def test_mark_failed_with_retries_remaining(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(
            db_session, alert.id, "email", "test@example.com", "Msg",
            max_attempts=3,
        )
        db_session.commit()

        mark_task_processing(db_session, task.id)
        mark_task_failed(db_session, task.id, "Connection timeout")

        task = db_session.get(NotificationTask, task.id)
        assert task.status == "failed"
        assert task.attempts == 1
        assert task.last_error == "Connection timeout"
        assert task.next_retry_at is not None
        assert task.next_retry_at > datetime.utcnow()

    def test_mark_failed_max_attempts_reached(self, db_session, setup_alert):
        alert = setup_alert
        task = enqueue_notification(
            db_session, alert.id, "email", "test@example.com", "Msg",
            max_attempts=1,
        )
        db_session.commit()

        mark_task_processing(db_session, task.id)
        mark_task_failed(db_session, task.id, "Final error")

        task = db_session.get(NotificationTask, task.id)
        assert task.status == "failed"
        assert task.attempts == 1

        # Alert should be marked failed
        alert = db_session.get(Alert, alert.id)
        assert alert.status == "failed"


class TestQueueStats:
    def test_empty_queue(self, db_session):
        stats = get_queue_stats(db_session)
        assert stats['pending'] == 0
        assert stats['processing'] == 0
        assert stats['completed'] == 0
        assert stats['failed'] == 0
        assert stats['retry_pending'] == 0

    def test_mixed_statuses(self, db_session, setup_alert):
        alert = setup_alert

        # Add tasks in various states
        t1 = enqueue_notification(db_session, alert.id, "email", "a@x.com", "M1")
        t2 = enqueue_notification(db_session, alert.id, "sms", "+1", "M2")
        t3 = enqueue_notification(db_session, alert.id, "telegram", "123", "M3")
        db_session.commit()

        mark_task_processing(db_session, t2.id)
        mark_task_completed(db_session, t2.id)

        mark_task_processing(db_session, t3.id)
        mark_task_failed(db_session, t3.id, "Error")

        stats = get_queue_stats(db_session)
        assert stats['pending'] == 1
        assert stats['completed'] == 1
        assert stats['failed'] == 1
        assert stats['retry_pending'] == 1  # t3 can still retry
