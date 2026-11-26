"""Console API: lists the demo journey folders and reproduces their expected outputs."""
from fastapi.testclient import TestClient

from trinetra_link.console.app import create_console_app


def test_console_lists_and_analyses_demo_inputs():
    client = TestClient(create_console_app())
    journeys = [j for j in client.get("/api/journeys").json() if j["group"] == "demo"]
    assert len(journeys) == 5
    for j in journeys:
        res = client.get(f"/api/analyze/{j['id']}").json()
        assert res["verdict"]["label"] == j["expected"]
        assert len(res["checkpoints"]) == 4


def test_console_rejects_paths_outside_journey_folders():
    client = TestClient(create_console_app())
    assert client.get("/api/analyze/demo:..").status_code == 404
    assert client.get("/api/image/demo:input1_Legitimate/../../pyproject.toml").status_code == 404
    assert client.get("/api/image/demo:input1_Legitimate/journey.json").status_code == 404
