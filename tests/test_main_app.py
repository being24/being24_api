from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"message": "Hello Bigger Applications!"}
