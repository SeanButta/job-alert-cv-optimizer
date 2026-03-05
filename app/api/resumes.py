from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select

from app.db.database import SessionLocal, Base, engine
from app.models.models import ResumeProfile, User
from app.services.resume_parser import parse_resume_bytes, MAX_FILE_MB

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _ensure_tables():
    Base.metadata.create_all(bind=engine)


class SetActiveRequest(BaseModel):
    job_type: str


@router.get("")
def list_resumes():
    _ensure_tables()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "demo@example.com"))
        if not user:
            return []
        rows = db.scalars(
            select(ResumeProfile).where(ResumeProfile.user_id == user.id).order_by(ResumeProfile.created_at.desc())
        ).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "job_type": r.job_type,
                "file_name": r.file_name,
                "file_type": r.file_type,
                "is_active": r.is_active,
                "parser_note": r.parser_note,
                "snippet": (r.extracted_text or "")[:220],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    name: str = Form(""),
    job_type: str = Form("general"),
):
    _ensure_tables()
    data = await file.read()
    if len(data) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_MB}MB")

    text, parser_note = parse_resume_bytes(file.filename or "resume.txt", data)
    if not text.strip():
        raise HTTPException(status_code=400, detail=f"Could not extract text ({parser_note}). Try TXT or another file.")

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "demo@example.com"))
        if not user:
            user = User(email="demo@example.com")
            db.add(user)
            db.flush()

        # deactivate currently active resume for same job_type
        active = db.scalars(
            select(ResumeProfile).where(
                ResumeProfile.user_id == user.id,
                ResumeProfile.job_type == job_type,
                ResumeProfile.is_active == True,
            )
        ).all()
        for a in active:
            a.is_active = False

        row = ResumeProfile(
            user_id=user.id,
            name=name or (file.filename or "Resume"),
            job_type=job_type or "general",
            file_name=file.filename or "resume",
            file_type=(file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else "txt",
            extracted_text=text,
            parser_note=parser_note,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"ok": True, "id": row.id, "parser_note": parser_note}
    finally:
        db.close()


@router.post("/{resume_id}/activate")
def activate_resume(resume_id: int, payload: SetActiveRequest):
    _ensure_tables()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "demo@example.com"))
        if not user:
            raise HTTPException(status_code=404, detail="User not seeded")

        row = db.scalar(select(ResumeProfile).where(ResumeProfile.id == resume_id, ResumeProfile.user_id == user.id))
        if not row:
            raise HTTPException(status_code=404, detail="Resume not found")

        job_type = payload.job_type or row.job_type or "general"
        others = db.scalars(
            select(ResumeProfile).where(
                ResumeProfile.user_id == user.id,
                ResumeProfile.job_type == job_type,
                ResumeProfile.is_active == True,
            )
        ).all()
        for o in others:
            o.is_active = False
        row.job_type = job_type
        row.is_active = True
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.delete("/{resume_id}")
def delete_resume(resume_id: int):
    _ensure_tables()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "demo@example.com"))
        if not user:
            return {"ok": True}
        row = db.scalar(select(ResumeProfile).where(ResumeProfile.id == resume_id, ResumeProfile.user_id == user.id))
        if row:
            db.delete(row)
            db.commit()
        return {"ok": True}
    finally:
        db.close()
