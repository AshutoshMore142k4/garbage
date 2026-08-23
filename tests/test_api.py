from fastapi.testclient import TestClient

from ledgerguard.api.app import app


def test_healthz_returns_200_with_expected_shape():
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["version"], str)
    assert isinstance(body["budget_spent_usd"], (int, float))
