import os
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from app.db.database import Base, engine, SessionLocal
from app.models.models import User, Resume, ResumeProfile, Preference, JobPost, Match, Alert, GeneratedDoc
from app.models.sources import JobSource  # Import to register model
from app.models.platform_settings import PlatformSetting  # Import to register model
from app.adapters.ingestion import sample_telegram_posts, fetch_telegram_posts_real
from app.services.matching import score_job
from app.services.scoring import compute_match_score
from app.services.recommender import generate_cv_recommendations
from app.services.docs import create_or_update_google_doc
from app.services.notifier import build_alert, dispatch_all
from app.services.dedupe import (
    compute_content_hash,
    compute_link_hash,
    is_duplicate_job,
    is_duplicate_alert,
    compute_alert_idempotency_key,
)
from app.services.reranker import rerank_match
from app.services.queue import enqueue_notification
from app.dashboard import router as dashboard_router
from app.api.sources import router as sources_router
from app.api.platforms import router as platforms_router
from app.api.resumes import router as resumes_router
from app.api.application_kit import router as application_kit_router

app = FastAPI(title='My Recruiting Agent')
Base.metadata.create_all(bind=engine)


def _ensure_jobpost_columns_sqlite():
    # Lightweight migration guard for existing sqlite DBs
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(job_posts)"))}
        if 'location' not in cols:
            conn.execute(text("ALTER TABLE job_posts ADD COLUMN location VARCHAR(255)"))
        if 'remote_type' not in cols:
            conn.execute(text("ALTER TABLE job_posts ADD COLUMN remote_type VARCHAR(50)"))
        if 'pay_band' not in cols:
            conn.execute(text("ALTER TABLE job_posts ADD COLUMN pay_band VARCHAR(255)"))
        if 'timezone' not in cols:
            conn.execute(text("ALTER TABLE job_posts ADD COLUMN timezone VARCHAR(100)"))


def _ensure_preference_columns_sqlite():
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(preferences)"))}
        if 'remote_only' not in cols:
            conn.execute(text("ALTER TABLE preferences ADD COLUMN remote_only BOOLEAN DEFAULT 0"))
        if 'preferred_locations' not in cols:
            conn.execute(text("ALTER TABLE preferences ADD COLUMN preferred_locations TEXT DEFAULT ''"))


_ensure_jobpost_columns_sqlite()
_ensure_preference_columns_sqlite()

# Include routers
app.include_router(dashboard_router)
app.include_router(sources_router)
app.include_router(platforms_router)
app.include_router(resumes_router)
app.include_router(application_kit_router)


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/seed')
def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.email == 'demo@example.com')):
            u = User(email='demo@example.com', phone='+15555550123', telegram_chat_id='demo-chat')
            db.add(u)
            db.flush()
            base_resume = '5 years backend engineering, FastAPI, Python, APIs'
            db.add(Resume(user_id=u.id, content=base_resume))
            db.add(ResumeProfile(user_id=u.id, name='Default Engineering Resume', job_type='engineering', file_name='seed.txt', file_type='txt', extracted_text=base_resume, is_active=True))
            db.add(ResumeProfile(user_id=u.id, name='General Resume', job_type='general', file_name='seed-general.txt', file_type='txt', extracted_text=base_resume, is_active=True))
            db.add(Preference(user_id=u.id, required_keywords='python,fastapi,sql', excluded_keywords='solidity', min_score=0.5))
            db.commit()
        return {'seeded': True}
    finally:
        db.close()


def _infer_job_type(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    if any(k in text for k in ["backend", "python", "engineer", "developer"]):
        return "engineering"
    if any(k in text for k in ["product", "pm", "manager"]):
        return "product"
    if any(k in text for k in ["sales", "business development", "account executive"]):
        return "sales"
    return "general"


def _get_resume_text(db, user_id: int, job_type: str) -> str:
    # Prefer active resume profile for exact job_type, then general
    row = db.scalar(
        select(ResumeProfile).where(
            ResumeProfile.user_id == user_id,
            ResumeProfile.job_type == job_type,
            ResumeProfile.is_active == True,
        ).order_by(ResumeProfile.created_at.desc())
    )
    if not row:
        row = db.scalar(
            select(ResumeProfile).where(
                ResumeProfile.user_id == user_id,
                ResumeProfile.job_type == 'general',
                ResumeProfile.is_active == True,
            ).order_by(ResumeProfile.created_at.desc())
        )
    if row and row.extracted_text:
        return row.extracted_text

    legacy = db.scalar(select(Resume).where(Resume.user_id == user_id))
    return legacy.content if legacy else ""


@app.post('/run-demo')
def run_demo():
    Base.metadata.create_all(bind=engine)
    """
    Main demo flow with Phase 2 enhancements:
    - Strong dedupe (content_hash, link_hash)
    - Idempotent alerts per user+job+channel
    - Optional LLM reranking
    - Queue-based notifications
    """
    db = SessionLocal()
    sent = []
    skipped_dedupe = []
    use_queue = os.getenv('ENABLE_QUEUE_NOTIFICATIONS', 'false').lower() == 'true'

    try:
        user = db.scalar(select(User).where(User.email == 'demo@example.com'))
        if not user:
            return {'error': 'Run /seed first'}

        pref = db.scalar(select(Preference).where(Preference.user_id == user.id))

        use_real_ingest = os.getenv('ENABLE_REAL_TELEGRAM_INGEST', 'false').lower() == 'true'
        posts = fetch_telegram_posts_real(limit=25) if use_real_ingest else sample_telegram_posts()

        for p in posts:
            # Compute hashes for strong dedupe
            content_hash = compute_content_hash(p['title'], p['description'], p['company'])
            link_hash = compute_link_hash(p['link'])

            # Check for duplicates (external_id, content_hash, or link_hash)
            is_dup, dup_reason = is_duplicate_job(db, p['external_id'], content_hash, link_hash)
            if is_dup:
                skipped_dedupe.append({'external_id': p['external_id'], 'reason': dup_reason})
                continue

            # Create job post with hashes
            job = JobPost(
                source=p['source'],
                external_id=p['external_id'],
                title=p['title'],
                company=p.get('company', ''),
                location=p.get('location'),
                remote_type=p.get('remote_type'),
                pay_band=p.get('pay_band'),
                timezone=p.get('timezone'),
                description=p['description'],
                link=p['link'],
                content_hash=content_hash,
                link_hash=link_hash,
            )
            db.add(job)
            db.flush()

            job_type = _infer_job_type(job.title, job.description)
            resume_text = _get_resume_text(db, user.id, job_type)

            required = [k.strip() for k in (pref.required_keywords or '').split(',') if k.strip()]
            excluded = [k.strip() for k in (pref.excluded_keywords or '').split(',') if k.strip()]
            preferred_locations = [x.strip() for x in (pref.preferred_locations or '').split(',') if x.strip()]

            breakdown = compute_match_score(
                job_title=job.title,
                job_description=job.description,
                job_company=job.company,
                cv_text=resume_text,
                required_keywords=required,
                excluded_keywords=excluded,
                user_prefers_remote=bool(pref.remote_only),
                remote_only=bool(pref.remote_only),
                preferred_locations=preferred_locations,
            )
            base_score = breakdown.total_score
            base_explain = breakdown.to_explanation_string()

            # Optional LLM reranking
            score, explain, llm_reranked = rerank_match(
                job.title, job.description,
                resume_text,
                base_score, base_explain,
            )

            if score < pref.min_score:
                continue

            # Create match
            m = Match(
                user_id=user.id,
                job_post_id=job.id,
                score=score,
                explanation=explain,
                llm_reranked=llm_reranked,
            )
            db.add(m)
            db.flush()

            # Generate CV recommendations and doc
            rec = generate_cv_recommendations(job.title, job.description, resume_text)
            doc_url = create_or_update_google_doc(user.id, rec, title=f'CV Tailor - {job.title}')
            gd = GeneratedDoc(user_id=user.id, match_id=m.id, doc_url=doc_url)
            db.add(gd)
            db.flush()

            # Build alert message
            msg = build_alert(job.title, job.link, score, doc_url)

            # Dispatch alerts with idempotency
            deliveries = []
            channels = []
            if user.email:
                channels.append(('email', user.email))
            if user.phone:
                channels.append(('sms', user.phone))
                channels.append(('whatsapp', user.phone))
            if user.telegram_chat_id:
                channels.append(('telegram', user.telegram_chat_id))

            for channel, target in channels:
                # Check idempotency - prevent duplicate alerts
                if is_duplicate_alert(db, user.id, job.id, channel):
                    deliveries.append({'channel': channel, 'status': 'skipped_duplicate'})
                    continue

                # Create alert record with idempotency key
                idempotency_key = compute_alert_idempotency_key(user.id, job.id, channel)
                alert = Alert(
                    user_id=user.id,
                    match_id=m.id,
                    channel=channel,
                    status='queued',
                    idempotency_key=idempotency_key,
                )
                db.add(alert)
                db.flush()

                if use_queue:
                    # Enqueue for async processing
                    enqueue_notification(db, alert.id, channel, target, msg)
                    deliveries.append({'channel': channel, 'status': 'queued'})
                else:
                    # Sync dispatch (original behavior)
                    from app.services.notifier import send_email, send_sms, send_telegram, send_whatsapp
                    dispatchers = {
                        'email': send_email,
                        'sms': send_sms,
                        'telegram': send_telegram,
                        'whatsapp': send_whatsapp,
                    }
                    result = dispatchers[channel](target, msg)
                    alert.status = result.get('status', 'unknown')
                    deliveries.append(result)

            sent.append({
                'job': job.title,
                'score': score,
                'llm_reranked': llm_reranked,
                'doc_url': doc_url,
                'deliveries': deliveries,
            })

        db.commit()
        return {
            'matches_sent': len(sent),
            'alerts': sent,
            'skipped_dedupe': skipped_dedupe,
            'real_ingest': use_real_ingest,
            'queue_mode': use_queue,
        }
    finally:
        db.close()


@app.get('/queue-stats')
def queue_stats():
    """Get notification queue statistics."""
    from app.services.queue import get_queue_stats
    db = SessionLocal()
    try:
        return get_queue_stats(db)
    finally:
        db.close()


@app.post('/api/test/sms')
def test_sms(
    phone: str = Query(..., description='Target phone in E.164 format, e.g. +15551234567'),
    message: str = Query('Test SMS from My Recruiting Agent ✅'),
    dry_run: bool = Query(False, description='When true, returns payload only and does not send'),
):
    """Quick connector verification endpoint for Twilio SMS."""
    from app.services.notifier import send_sms

    if dry_run:
        return {
            'ok': True,
            'mode': 'dry_run',
            'channel': 'sms',
            'target': phone,
            'message': message,
            'note': 'No SMS sent. Set dry_run=false to attempt delivery.'
        }

    result = send_sms(phone, message)
    return {
        'ok': result.get('status') in ('sent', 'mock_sent'),
        'result': result,
        'hint': 'For real delivery, set ENABLE_REAL_NOTIFICATIONS=true and Twilio env vars.'
    }
