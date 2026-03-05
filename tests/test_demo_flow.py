from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_demo_flow():
    assert client.post('/seed').status_code==200
    r=client.post('/run-demo')
    assert r.status_code==200
    assert 'matches_sent' in r.json()
