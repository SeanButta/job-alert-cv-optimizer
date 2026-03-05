from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_resume_upload_list_activate_delete():
    client.post('/seed')

    files = {'file': ('resume.txt', b'Python FastAPI SQL backend', 'text/plain')}
    data = {'name': 'Backend CV', 'job_type': 'engineering'}
    up = client.post('/api/resumes/upload', files=files, data=data)
    assert up.status_code == 200
    rid = up.json()['id']

    ls = client.get('/api/resumes')
    assert ls.status_code == 200
    arr = ls.json()
    assert any(r['id'] == rid for r in arr)

    act = client.post(f'/api/resumes/{rid}/activate', json={'job_type': 'engineering'})
    assert act.status_code == 200

    dele = client.delete(f'/api/resumes/{rid}')
    assert dele.status_code == 200
