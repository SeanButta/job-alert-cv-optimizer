from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db.database import Base

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    email: Mapped[str]=mapped_column(String(255), unique=True)
    phone: Mapped[str|None]=mapped_column(String(50), nullable=True)
    telegram_chat_id: Mapped[str|None]=mapped_column(String(100), nullable=True)
    whatsapp_id: Mapped[str|None]=mapped_column(String(100), nullable=True)

class Resume(Base):
    __tablename__='resumes'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    content: Mapped[str]=mapped_column(Text)

class Preference(Base):
    __tablename__='preferences'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    required_keywords: Mapped[str]=mapped_column(Text, default='')
    excluded_keywords: Mapped[str]=mapped_column(Text, default='')
    min_score: Mapped[float]=mapped_column(Float, default=0.5)

class JobPost(Base):
    __tablename__='job_posts'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    source: Mapped[str]=mapped_column(String(50))
    external_id: Mapped[str]=mapped_column(String(255), unique=True)
    title: Mapped[str]=mapped_column(String(255))
    company: Mapped[str]=mapped_column(String(255), default='')
    description: Mapped[str]=mapped_column(Text)
    link: Mapped[str]=mapped_column(String(1000))
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)

class Match(Base):
    __tablename__='matches'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    job_post_id: Mapped[int]=mapped_column(ForeignKey('job_posts.id'))
    score: Mapped[float]=mapped_column(Float)
    explanation: Mapped[str]=mapped_column(Text)

class Alert(Base):
    __tablename__='alerts'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    match_id: Mapped[int]=mapped_column(ForeignKey('matches.id'))
    channel: Mapped[str]=mapped_column(String(30))
    status: Mapped[str]=mapped_column(String(30), default='queued')

class GeneratedDoc(Base):
    __tablename__='generated_docs'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    match_id: Mapped[int]=mapped_column(ForeignKey('matches.id'))
    doc_url: Mapped[str]=mapped_column(String(1000))

class AuditLog(Base):
    __tablename__='audit_logs'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    event_type: Mapped[str]=mapped_column(String(100))
    payload: Mapped[str]=mapped_column(Text)
    idempotency_key: Mapped[str]=mapped_column(String(255), unique=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, default=datetime.utcnow)
