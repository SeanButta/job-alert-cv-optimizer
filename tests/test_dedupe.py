"""Tests for strong deduplication logic."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.models import JobPost, Alert, User, Match
from app.services.dedupe import (
    compute_content_hash,
    compute_link_hash,
    compute_alert_idempotency_key,
    is_duplicate_job,
    is_duplicate_alert,
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


class TestContentHash:
    def test_same_content_same_hash(self):
        h1 = compute_content_hash("Python Dev", "Looking for Python developer", "Acme")
        h2 = compute_content_hash("Python Dev", "Looking for Python developer", "Acme")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("PYTHON DEV", "LOOKING FOR PYTHON DEVELOPER", "ACME")
        h2 = compute_content_hash("python dev", "looking for python developer", "acme")
        assert h1 == h2

    def test_whitespace_normalized(self):
        h1 = compute_content_hash("Python Dev  ", "  Looking for Python developer  ", "  Acme")
        h2 = compute_content_hash("Python Dev", "Looking for Python developer", "Acme")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_content_hash("Python Dev", "Looking for Python developer", "Acme")
        h2 = compute_content_hash("Java Dev", "Looking for Java developer", "Acme")
        assert h1 != h2


class TestLinkHash:
    def test_same_link_same_hash(self):
        h1 = compute_link_hash("https://example.com/jobs/123")
        h2 = compute_link_hash("https://example.com/jobs/123")
        assert h1 == h2

    def test_trailing_slash_normalized(self):
        h1 = compute_link_hash("https://example.com/jobs/123/")
        h2 = compute_link_hash("https://example.com/jobs/123")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_link_hash("HTTPS://EXAMPLE.COM/jobs/123")
        h2 = compute_link_hash("https://example.com/jobs/123")
        assert h1 == h2

    def test_utm_params_removed(self):
        h1 = compute_link_hash("https://example.com/jobs/123?utm_source=twitter&utm_medium=social")
        h2 = compute_link_hash("https://example.com/jobs/123")
        assert h1 == h2

    def test_fbclid_removed(self):
        h1 = compute_link_hash("https://example.com/jobs/123?fbclid=abc123")
        h2 = compute_link_hash("https://example.com/jobs/123")
        assert h1 == h2


class TestIsDuplicateJob:
    def test_no_duplicates(self, db_session):
        is_dup, reason = is_duplicate_job(db_session, "ext-1", "hash1", "link1")
        assert is_dup is False
        assert reason is None

    def test_external_id_duplicate(self, db_session):
        job = JobPost(
            source="telegram", external_id="ext-1",
            title="Dev", company="Acme", description="Job", link="https://example.com",
            content_hash="old_hash", link_hash="old_link",
        )
        db_session.add(job)
        db_session.commit()

        is_dup, reason = is_duplicate_job(db_session, "ext-1", "new_hash", "new_link")
        assert is_dup is True
        assert reason == "external_id"

    def test_content_hash_duplicate(self, db_session):
        job = JobPost(
            source="telegram", external_id="ext-1",
            title="Dev", company="Acme", description="Job", link="https://example.com",
            content_hash="same_content", link_hash="link1",
        )
        db_session.add(job)
        db_session.commit()

        # Same content but different external_id
        is_dup, reason = is_duplicate_job(db_session, "ext-2", "same_content", "link2")
        assert is_dup is True
        assert reason == "content_hash"

    def test_link_hash_duplicate(self, db_session):
        job = JobPost(
            source="telegram", external_id="ext-1",
            title="Dev", company="Acme", description="Job", link="https://example.com",
            content_hash="hash1", link_hash="same_link",
        )
        db_session.add(job)
        db_session.commit()

        # Same link but different external_id and content
        is_dup, reason = is_duplicate_job(db_session, "ext-2", "hash2", "same_link")
        assert is_dup is True
        assert reason == "link_hash"


class TestAlertIdempotency:
    def test_idempotency_key_format(self):
        key = compute_alert_idempotency_key(1, 100, "email")
        assert key == "alert:1:100:email"

    def test_different_users_different_keys(self):
        k1 = compute_alert_idempotency_key(1, 100, "email")
        k2 = compute_alert_idempotency_key(2, 100, "email")
        assert k1 != k2

    def test_different_jobs_different_keys(self):
        k1 = compute_alert_idempotency_key(1, 100, "email")
        k2 = compute_alert_idempotency_key(1, 101, "email")
        assert k1 != k2

    def test_different_channels_different_keys(self):
        k1 = compute_alert_idempotency_key(1, 100, "email")
        k2 = compute_alert_idempotency_key(1, 100, "telegram")
        assert k1 != k2

    def test_is_duplicate_alert(self, db_session):
        # Setup user and match
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

        # First alert - not duplicate
        assert is_duplicate_alert(db_session, user.id, job.id, "email") is False

        # Add alert with idempotency key
        key = compute_alert_idempotency_key(user.id, job.id, "email")
        alert = Alert(
            user_id=user.id, match_id=match.id,
            channel="email", status="sent",
            idempotency_key=key,
        )
        db_session.add(alert)
        db_session.commit()

        # Now it should be duplicate
        assert is_duplicate_alert(db_session, user.id, job.id, "email") is True

        # Different channel - not duplicate
        assert is_duplicate_alert(db_session, user.id, job.id, "telegram") is False
