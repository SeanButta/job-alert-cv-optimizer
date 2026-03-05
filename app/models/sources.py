"""
Job source data models.

Supports three source types:
- telegram_channel: Telegram channels/groups to monitor for job posts
- website: Website URLs to scrape for job listings
- linkedin_recruiter: LinkedIn recruiters to track for job postings
"""
from sqlalchemy import String, Text, Integer, DateTime, Enum, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum as PyEnum

from app.db.database import Base


class SourceType(str, PyEnum):
    """Supported job source types."""
    TELEGRAM_CHANNEL = "telegram_channel"
    TELEGRAM_PUBLIC = "telegram_public"  # No bot token required
    WEBSITE = "website"
    LINKEDIN_RECRUITER = "linkedin_recruiter"


class SourceStatus(str, PyEnum):
    """Source status states."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class JobSource(Base):
    """
    User-configurable job source.
    
    Attributes:
        type: Source type (telegram_channel, website, linkedin_recruiter)
        identifier: Unique identifier for the source
            - telegram_channel: channel username or invite link (@channel or t.me/joinchat/xxx)
            - website: URL of the job board/page
            - linkedin_recruiter: LinkedIn profile URL or recruiter name
        name: User-friendly display name
        status: active/inactive/error
        user_id: Owner user (optional, NULL = global source)
        config: JSON config for source-specific settings
        last_checked: Last successful check timestamp
        last_error: Last error message if any
        error_count: Consecutive error count (resets on success)
    """
    __tablename__ = 'job_sources'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=SourceStatus.ACTIVE.value)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON config
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_job_sources_type_status', 'type', 'status'),
        Index('ix_job_sources_user_id', 'user_id'),
        Index('ix_job_sources_identifier', 'identifier'),
    )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'id': self.id,
            'type': self.type,
            'identifier': self.identifier,
            'name': self.name,
            'status': self.status,
            'user_id': self.user_id,
            'config': self.config,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'last_error': self.last_error,
            'error_count': self.error_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
