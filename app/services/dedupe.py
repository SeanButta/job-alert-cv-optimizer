"""
Strong deduplication service for job posts.

Uses content hash and link hash in addition to external_id to catch:
- Same job posted under different external IDs
- Same job link posted multiple times
- Near-duplicate posts (same content, different metadata)
"""
import hashlib
from typing import Optional, Tuple


def compute_content_hash(title: str, description: str, company: str) -> str:
    """Compute SHA-256 hash of normalized job content."""
    normalized = f"{title.lower().strip()}|{description.lower().strip()}|{company.lower().strip()}"
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def compute_link_hash(link: str) -> str:
    """Compute SHA-256 hash of normalized link."""
    # Normalize: lowercase, strip trailing slashes, remove common tracking params
    normalized = link.lower().strip().rstrip('/')
    # Remove common tracking params
    for param in ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'fbclid', 'gclid']:
        if f'?{param}=' in normalized or f'&{param}=' in normalized:
            import re
            normalized = re.sub(rf'[?&]{param}=[^&]*', '', normalized)
    normalized = normalized.rstrip('?&')
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def compute_alert_idempotency_key(user_id: int, job_post_id: int, channel: str) -> str:
    """Generate idempotency key for user+job+channel combo to prevent duplicate alerts."""
    return f"alert:{user_id}:{job_post_id}:{channel}"


def is_duplicate_job(
    db_session,
    external_id: str,
    content_hash: str,
    link_hash: str
) -> Tuple[bool, Optional[str]]:
    """
    Check if job is duplicate by external_id, content_hash, or link_hash.
    Returns (is_duplicate, reason).
    """
    from app.models.models import JobPost
    from sqlalchemy import select

    # Check external_id first (fastest, indexed)
    if db_session.scalar(select(JobPost).where(JobPost.external_id == external_id)):
        return True, 'external_id'

    # Check content hash (catches same job under different ID)
    if db_session.scalar(select(JobPost).where(JobPost.content_hash == content_hash)):
        return True, 'content_hash'

    # Check link hash (catches same link posted multiple times)
    if db_session.scalar(select(JobPost).where(JobPost.link_hash == link_hash)):
        return True, 'link_hash'

    return False, None


def is_duplicate_alert(db_session, user_id: int, job_post_id: int, channel: str) -> bool:
    """Check if alert already exists for user+job+channel combo."""
    from app.models.models import Alert
    from sqlalchemy import select

    idempotency_key = compute_alert_idempotency_key(user_id, job_post_id, channel)
    return db_session.scalar(
        select(Alert).where(Alert.idempotency_key == idempotency_key)
    ) is not None
