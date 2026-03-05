from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_resume_preferences_roundtrip():
    client.post('/seed')
    r = client.post('/api/resumes/preferences', json={
        'remote_only': True,
        'preferred_locations': 'Chicago, New York City, San Francisco'
    })
    assert r.status_code == 200

    g = client.get('/api/resumes/preferences')
    assert g.status_code == 200
    body = g.json()
    assert body['remote_only'] is True
    assert 'Chicago' in body['preferred_locations']
