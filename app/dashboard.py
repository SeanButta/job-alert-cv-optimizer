"""
Mobile-friendly dashboard for Job Alert system.

Shows recent jobs, matches, alerts, sources, and queue status.
"""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, desc
from pathlib import Path

from app.db.database import SessionLocal
from app.models.models import JobPost, Match, Alert, GeneratedDoc, User, NotificationTask, ResumeProfile, ApplicationKitArtifact
from app.models.sources import JobSource, SourceStatus
from app.services.queue import get_queue_stats

router = APIRouter()

# Templates directory
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def get_dashboard_data():
    """Gather all data for dashboard display."""
    db = SessionLocal()
    try:
        # Basic stats
        total_jobs = db.scalar(select(func.count(JobPost.id))) or 0
        total_matches = db.scalar(select(func.count(Match.id))) or 0
        alerts_sent = db.scalar(
            select(func.count(Alert.id)).where(Alert.status.in_(['sent', 'mock_sent', 'completed']))
        ) or 0

        # Queue stats
        queue_stats = get_queue_stats(db)

        # Source stats
        active_sources = db.scalar(
            select(func.count(JobSource.id)).where(JobSource.status == SourceStatus.ACTIVE.value)
        ) or 0
        total_sources = db.scalar(select(func.count(JobSource.id))) or 0
        error_sources = db.scalar(
            select(func.count(JobSource.id)).where(JobSource.status == SourceStatus.ERROR.value)
        ) or 0

        source_stats = {
            'active': active_sources,
            'total': total_sources,
            'error': error_sources,
        }

        # Get all sources for display
        sources_raw = list(db.scalars(
            select(JobSource).order_by(desc(JobSource.created_at))
        ).all())
        sources = []
        for s in sources_raw:
            data = s.to_dict()
            # Parse JSON config if present
            if data.get('config'):
                try:
                    data['config'] = json.loads(data['config'])
                except (json.JSONDecodeError, TypeError):
                    pass
            sources.append(data)

        # Recent jobs (last 20)
        recent_jobs = list(db.scalars(
            select(JobPost).order_by(desc(JobPost.created_at)).limit(20)
        ).all())

        # Recent matches with user/job info (last 20)
        matches_query = (
            select(
                Match.id,
                Match.score,
                Match.explanation,
                Match.llm_reranked,
                Match.user_id,
                Match.job_post_id,
                User.email.label('user_email'),
                JobPost.title.label('job_title'),
            )
            .join(User, Match.user_id == User.id)
            .join(JobPost, Match.job_post_id == JobPost.id)
            .order_by(desc(Match.id))
            .limit(20)
        )
        recent_matches_raw = db.execute(matches_query).all()

        # Get doc URLs for matches
        match_ids = [m.id for m in recent_matches_raw]
        docs = {
            d.match_id: d.doc_url
            for d in db.scalars(
                select(GeneratedDoc).where(GeneratedDoc.match_id.in_(match_ids))
            ).all()
        } if match_ids else {}

        recent_matches = [
            {
                'id': m.id,
                'score': m.score,
                'explanation': m.explanation,
                'llm_reranked': m.llm_reranked,
                'user_email': m.user_email,
                'job_title': m.job_title,
                'doc_url': docs.get(m.id),
            }
            for m in recent_matches_raw
        ]

        # Resume profiles (for resume tab)
        resumes = [
            {
                'id': r.id,
                'name': r.name,
                'job_type': r.job_type,
                'file_name': r.file_name,
                'file_type': r.file_type,
                'is_active': r.is_active,
                'parser_note': r.parser_note,
                'snippet': (r.extracted_text or '')[:220],
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in db.scalars(select(ResumeProfile).order_by(desc(ResumeProfile.created_at)).limit(50)).all()
        ]

        # Recent application kit artifacts
        recent_artifacts = [
            {
                'id': a.id,
                'artifact_type': a.artifact_type,
                'title': a.title,
                'created_at': a.created_at.isoformat() if a.created_at else None,
                'content': a.content,
            }
            for a in db.scalars(
                select(ApplicationKitArtifact).order_by(desc(ApplicationKitArtifact.created_at)).limit(20)
            ).all()
        ]

        # Recent alerts with user/job info (last 30)
        alerts_query = (
            select(
                Alert.id,
                Alert.channel,
                Alert.status,
                User.email.label('user_email'),
                JobPost.title.label('job_title'),
                JobPost.company.label('company'),
                JobPost.location.label('location'),
                JobPost.remote_type.label('remote_type'),
                JobPost.pay_band.label('pay_band'),
                JobPost.timezone.label('timezone'),
                Match.score.label('match_score'),
            )
            .join(User, Alert.user_id == User.id)
            .join(Match, Alert.match_id == Match.id)
            .join(JobPost, Match.job_post_id == JobPost.id)
            .order_by(desc(Alert.id))
            .limit(30)
        )
        recent_alerts = [
            {
                'id': a.id,
                'channel': a.channel,
                'status': a.status,
                'user_email': a.user_email,
                'job_title': a.job_title,
                'company': a.company,
                'location': a.location,
                'remote_type': a.remote_type,
                'pay_band': a.pay_band,
                'timezone': a.timezone,
                'match_score': a.match_score,
            }
            for a in db.execute(alerts_query).all()
        ]

        return {
            'stats': {
                'total_jobs': total_jobs,
                'total_matches': total_matches,
                'alerts_sent': alerts_sent,
                'queue_pending': queue_stats.get('pending', 0) + queue_stats.get('retry_pending', 0),
                'queue_failed': queue_stats.get('failed', 0) - queue_stats.get('retry_pending', 0),
            },
            'queue_stats': queue_stats,
            'source_stats': source_stats,
            'sources': sources,
            'recent_jobs': recent_jobs,
            'recent_matches': recent_matches,
            'recent_alerts': recent_alerts,
            'resumes': resumes,
            'recent_artifacts': recent_artifacts,
        }
    finally:
        db.close()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render mobile-friendly dashboard."""
    data = get_dashboard_data()
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})


@router.get("/api/dashboard")
async def dashboard_api():
    """JSON API endpoint for dashboard data."""
    data = get_dashboard_data()
    # Convert JobPost objects to dicts for JSON serialization
    data['recent_jobs'] = [
        {
            'id': j.id,
            'title': j.title,
            'company': j.company,
            'source': j.source,
            'link': j.link,
            'created_at': j.created_at.isoformat() if j.created_at else None,
        }
        for j in data['recent_jobs']
    ]
    return data
