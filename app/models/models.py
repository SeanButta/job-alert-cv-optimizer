from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    whatsapp_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Resume(Base):
    __tablename__ = 'resumes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    content: Mapped[str] = mapped_column(Text)


class ResumeProfile(Base):
    __tablename__ = 'resume_profiles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(255), default='Resume')
    job_type: Mapped[str] = mapped_column(String(100), default='general', index=True)
    file_name: Mapped[str] = mapped_column(String(255), default='resume.txt')
    file_type: Mapped[str] = mapped_column(String(50), default='txt')
    extracted_text: Mapped[str] = mapped_column(Text)
    parser_note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Preference(Base):
    __tablename__ = 'preferences'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    required_keywords: Mapped[str] = mapped_column(Text, default='')
    excluded_keywords: Mapped[str] = mapped_column(Text, default='')
    min_score: Mapped[float] = mapped_column(Float, default=0.5)


class JobPost(Base):
    __tablename__ = 'job_posts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    company: Mapped[str] = mapped_column(String(255), default='')
    location: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    remote_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)  # remote | hybrid | onsite
    pay_band: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    timezone: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    description: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    link_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = 'matches'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    job_post_id: Mapped[int] = mapped_column(ForeignKey('job_posts.id'))
    score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    llm_reranked: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    match_id: Mapped[int] = mapped_column(ForeignKey('matches.id'))
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)


class GeneratedDoc(Base):
    __tablename__ = 'generated_docs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    match_id: Mapped[int] = mapped_column(ForeignKey('matches.id'))
    doc_url: Mapped[str] = mapped_column(String(1000))


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationTask(Base):
    """SQLite-backed job queue for notification tasks with retry support."""
    __tablename__ = 'notification_tasks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey('alerts.id'))
    channel: Mapped[str] = mapped_column(String(30))
    target: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='pending')  # pending, processing, completed, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_notification_tasks_status_retry', 'status', 'next_retry_at'),
    )
