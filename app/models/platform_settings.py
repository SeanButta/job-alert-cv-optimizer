"""
Platform toggle settings model.

Stores per-user or global enable/disable state for job platforms.
"""
from sqlalchemy import String, Integer, DateTime, Boolean, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.db.database import Base


class PlatformSetting(Base):
    """
    User-configurable platform enable/disable settings.
    
    Attributes:
        platform: Platform type identifier (e.g., 'wellfound', 'linkedin_jobs')
        enabled: Whether this platform is enabled for polling
        user_id: Owner user (NULL = global default setting)
        last_checked: Last successful check timestamp for this platform
        last_error: Last error message if any
        error_count: Consecutive error count
    """
    __tablename__ = 'platform_settings'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('platform', 'user_id', name='uq_platform_user'),
        Index('ix_platform_settings_enabled', 'enabled'),
        Index('ix_platform_settings_user', 'user_id'),
    )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'id': self.id,
            'platform': self.platform,
            'enabled': self.enabled,
            'user_id': self.user_id,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'last_error': self.last_error,
            'error_count': self.error_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
