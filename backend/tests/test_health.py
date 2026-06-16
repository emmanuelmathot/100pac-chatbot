def test_health_endpoint_returns_healthy(test_client):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Healthy!"
