def test_health_and_empty_dashboard(client):
    assert client.get("/health/live").status_code == 200
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    assert response.json()["game_count"] == 0


def test_import_creates_profile_and_deduplicates_active_job(client):
    first = client.post("/api/v1/imports/chess-com", json={"username": "demo_player"})
    second = client.post("/api/v1/imports/chess-com", json={"username": "DEMO_PLAYER"})
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert second.json()["deduplicated"] is True

