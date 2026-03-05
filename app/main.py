from fastapi import FastAPI
from sqlalchemy import select
from app.db.database import Base, engine, SessionLocal
from app.models.models import User, Resume, Preference, JobPost, Match, Alert, GeneratedDoc
from app.adapters.ingestion import sample_telegram_posts
from app.services.matching import score_job
from app.services.recommender import generate_cv_recommendations
from app.services.docs import create_or_update_google_doc_mock
from app.services.notifier import build_alert, send_mock

app=FastAPI(title='Job Alert CV Optimizer')
Base.metadata.create_all(bind=engine)

@app.get('/health')
def health():
    return {'ok':True}

@app.post('/seed')
def seed():
    db=SessionLocal()
    try:
        if not db.scalar(select(User).where(User.email=='demo@example.com')):
            u=User(email='demo@example.com',telegram_chat_id='demo-chat')
            db.add(u); db.flush()
            db.add(Resume(user_id=u.id, content='5 years backend engineering, FastAPI, Python, APIs'))
            db.add(Preference(user_id=u.id, required_keywords='python,fastapi,sql', excluded_keywords='solidity', min_score=0.5))
            db.commit()
        return {'seeded':True}
    finally:
        db.close()

@app.post('/run-demo')
def run_demo():
    db=SessionLocal(); sent=[]
    try:
        user=db.scalar(select(User).where(User.email=='demo@example.com'))
        resume=db.scalar(select(Resume).where(Resume.user_id==user.id))
        pref=db.scalar(select(Preference).where(Preference.user_id==user.id))
        for p in sample_telegram_posts():
            if db.scalar(select(JobPost).where(JobPost.external_id==p['external_id'])):
                continue
            job=JobPost(**p); db.add(job); db.flush()
            score,explain=score_job(job.description,resume.content,pref.required_keywords,pref.excluded_keywords)
            if score >= pref.min_score:
                m=Match(user_id=user.id,job_post_id=job.id,score=score,explanation=explain); db.add(m); db.flush()
                rec=generate_cv_recommendations(job.title,job.description,resume.content)
                doc_url=create_or_update_google_doc_mock(user.id,rec)
                gd=GeneratedDoc(user_id=user.id,match_id=m.id,doc_url=doc_url); db.add(gd); db.flush()
                msg=build_alert(job.title,job.link,score,doc_url)
                send=send_mock('telegram', user.telegram_chat_id or 'demo', msg)
                db.add(Alert(user_id=user.id,match_id=m.id,channel='telegram',status='mock_sent'))
                sent.append({'job':job.title,'score':score,'doc_url':doc_url,'notification':send})
        db.commit()
        return {'matches_sent':len(sent),'alerts':sent}
    finally:
        db.close()
