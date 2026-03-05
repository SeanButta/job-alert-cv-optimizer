from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_sms_dry_run():
    r = client.post('/api/test/sms', params={'phone': '+15555550123', 'dry_run': 'true'})
    assert r.status_code == 200
    body = r.json()
    assert body['ok'] is True
    assert body['mode'] == 'dry_run'
