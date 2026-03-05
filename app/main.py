import os
from fastapi import FastAPI
from sqlalchemy import select
from app.db.database import Base, engine, SessionLocal
from app.models.models import User, Resume, Preference, JobPost, Match, Alert, GeneratedDoc
from app.adapters.ingestion import sample_telegram_posts, fetch_telegram_posts_real
from app.services.matching import score_job
from app.services.recommender import generate_cv_recommendations
from app.services.docs import create_or_update_google_doc
from app.services.notifier import build_alert, dispatch_all

app = FastAPI(title='Job Alert CV Optimizer')
Base.metadata.create_all(bind=engine)

@app.get('/health')
def health():
    return {'ok': True}

@app.post('/seed')
def seed():
    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.email == 'demo@example.com')):
            u = User(email='demo@example.com', phone='+15555550123', telegram_chat_id='demo-chat')
            db.add(u); db.flush()
            db.add(Resume(user_id=u.id, content='5 years backend engineering, FastAPI, Python, APIs'))
            db.add(Preference(user_id=u.id, required_keywords='python,fastapi,sql', excluded_keywords='solidity', min_score=0.5))
            db.commit()
        return {'seeded': True}
    finally:
        db.close()

@app.post('/run-demo')
def run_demo():
    db = SessionLocal(); sent = []
    try:
        user = db.scalar(select(User).where(User.email == 'demo@example.com'))
        resume = db.scalar(select(Resume).where(Resume.user_id == user.id))
        pref = db.scalar(select(Preference).where(Preference.user_id == user.id))

        use_real_ingest = os.getenv('ENABLE_REAL_TELEGRAM_INGEST', 'false').lower() == 'true'
        posts = fetch_telegram_posts_real(limit=25) if use_real_ingest else sample_telegram_posts()

        for p in posts:
            if db.scalar(select(JobPost).where(JobPost.external_id == p['external_id'])):
                continue

            job = JobPost(**p); db.add(job); db.flush()
            score, explain = score_job(job.description, resume.content, pref.required_keywords, pref.excluded_keywords)
            if score < pref.min_score:
                continue

            m = Match(user_id=user.id, job_post_id=job.id, score=score, explanation=explain)
            db.add(m); db.flush()

            rec = generate_cv_recommendations(job.title, job.description, resume.content)
            doc_url = create_or_update_google_doc(user.id, rec, title=f'CV Tailor - {job.title}')
            gd = GeneratedDoc(user_id=user.id, match_id=m.id, doc_url=doc_url)
            db.add(gd); db.flush()

            msg = build_alert(job.title, job.link, score, doc_url)
            deliveries = dispatch_all(
                {'email': user.email, 'phone': user.phone, 'telegram_chat_id': user.telegram_chat_id},
                msg,
            )

            for d in deliveries:
                db.add(Alert(user_id=user.id, match_id=m.id, channel=d['channel'], status=d['status']))

            sent.append({'job': job.title, 'score': score, 'doc_url': doc_url, 'deliveries': deliveries})

        db.commit()
        return {'matches_sent': len(sent), 'alerts': sent, 'real_ingest': use_real_ingest}
    finally:
        db.close()
