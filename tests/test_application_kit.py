from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_application_kit_generation_flow():
    client.post('/seed')
    client.post('/run-demo')

    jobs_resp = client.get('/api/application-kit/jobs')
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json().get('jobs', [])
    assert len(jobs) > 0

    resumes_resp = client.get('/api/application-kit/resumes')
    assert resumes_resp.status_code == 200
    resumes = resumes_resp.json().get('resumes', [])
    assert len(resumes) > 0

    payload = {
        'job_post_id': jobs[0]['id'],
        'resume_profile_id': resumes[0]['id'],
        'artifact_types': ['resume', 'cover_letter', 'interview_prep']
    }
    gen_resp = client.post('/api/application-kit/generate', json=payload)
    assert gen_resp.status_code == 200
    body = gen_resp.json()
    assert body['ok'] is True
    assert len(body['artifacts']) == 3

    hist_resp = client.get('/api/application-kit/history')
    assert hist_resp.status_code == 200
    assert len(hist_resp.json().get('history', [])) >= 3
