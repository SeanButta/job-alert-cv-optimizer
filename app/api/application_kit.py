from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc

from app.db.database import SessionLocal
from app.models.models import User, JobPost, ResumeProfile, ApplicationKitArtifact
from app.services.application_kit import (
    generate_tailored_resume,
    generate_cover_letter,
    generate_interview_prep,
)

router = APIRouter(prefix='/api/application-kit', tags=['application-kit'])


class GenerateKitRequest(BaseModel):
    job_post_id: int
    resume_profile_id: int | None = None
    artifact_types: list[str] = ['resume', 'cover_letter', 'interview_prep']


@router.get('/jobs')
def list_jobs(limit: int = 50):
    db = SessionLocal()
    try:
        jobs = db.scalars(select(JobPost).order_by(desc(JobPost.created_at)).limit(limit)).all()
        return {
            'jobs': [
                {
                    'id': j.id,
                    'title': j.title,
                    'company': j.company,
                    'location': j.location,
                    'remote_type': j.remote_type,
                    'created_at': j.created_at.isoformat() if j.created_at else None,
                }
                for j in jobs
            ]
        }
    finally:
        db.close()


@router.get('/resumes')
def list_resumes(limit: int = 100):
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == 'demo@example.com'))
        if not user:
            return {'resumes': []}
        rows = db.scalars(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == user.id)
            .order_by(desc(ResumeProfile.created_at))
            .limit(limit)
        ).all()
        return {
            'resumes': [
                {
                    'id': r.id,
                    'name': r.name,
                    'job_type': r.job_type,
                    'is_active': r.is_active,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@router.get('/history')
def history(limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.scalars(select(ApplicationKitArtifact).order_by(desc(ApplicationKitArtifact.created_at)).limit(limit)).all()
        return {
            'history': [
                {
                    'id': a.id,
                    'artifact_type': a.artifact_type,
                    'title': a.title,
                    'job_post_id': a.job_post_id,
                    'resume_profile_id': a.resume_profile_id,
                    'created_at': a.created_at.isoformat() if a.created_at else None,
                    'content': a.content,
                }
                for a in rows
            ]
        }
    finally:
        db.close()


@router.post('/generate')
def generate(payload: GenerateKitRequest):
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == 'demo@example.com'))
        if not user:
            raise HTTPException(status_code=400, detail='Run /seed first')

        job = db.scalar(select(JobPost).where(JobPost.id == payload.job_post_id))
        if not job:
            raise HTTPException(status_code=404, detail='Job not found')

        resume_profile = None
        if payload.resume_profile_id:
            resume_profile = db.scalar(
                select(ResumeProfile).where(
                    ResumeProfile.id == payload.resume_profile_id,
                    ResumeProfile.user_id == user.id,
                )
            )
            if not resume_profile:
                raise HTTPException(status_code=404, detail='Resume profile not found')
        else:
            resume_profile = db.scalar(
                select(ResumeProfile).where(
                    ResumeProfile.user_id == user.id,
                    ResumeProfile.is_active == True,
                ).order_by(desc(ResumeProfile.created_at))
            )

        resume_text = (resume_profile.extracted_text if resume_profile else '') or ''
        company = job.company or 'Target Company'

        out = []
        for t in payload.artifact_types:
            t = t.strip().lower()
            if t == 'resume':
                content = generate_tailored_resume(resume_text, job.title, company, job.description)
                title = f"Tailored Resume - {job.title}"
            elif t == 'cover_letter':
                content = generate_cover_letter(resume_text, job.title, company, job.description)
                title = f"Cover Letter - {job.title}"
            elif t == 'interview_prep':
                content = generate_interview_prep(resume_text, job.title, company, job.description)
                title = f"Interview Prep - {job.title}"
            else:
                continue

            row = ApplicationKitArtifact(
                user_id=user.id,
                job_post_id=job.id,
                resume_profile_id=resume_profile.id if resume_profile else None,
                artifact_type=t,
                title=title,
                content=content,
            )
            db.add(row)
            db.flush()
            out.append({
                'id': row.id,
                'artifact_type': t,
                'title': title,
                'content': content,
            })

        db.commit()
        return {'ok': True, 'artifacts': out}
    finally:
        db.close()
