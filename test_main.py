from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

client = TestClient(app)


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_election_timeline_validation_error_empty_payload():
    # Empty payload should trigger a 422 Unprocessable Entity
    response = client.post("/api/election-timeline", json={})
    assert response.status_code == 422


def test_election_timeline_validation_error_invalid_zip():
    # Invalid zip code length should trigger a 422
    response = client.post("/api/election-timeline", json={"zip_code": "123", "query": "How to register?"})
    assert response.status_code == 422


@patch("main.genai_client")
def test_election_timeline_success(mock_genai_client):
    # Configure the mock response
    mock_response = MagicMock()
    mock_response.text = '{"steps": [{"step": 1, "action": "Check Status", "details": "Verify your voter registration status online."}]}'

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_genai_client.models = mock_models

    # Valid payload
    payload = {
        "zip_code": "12345",
        "query": "How do I register to vote in my county?"
    }

    # Make the request
    response = client.post("/api/election-timeline", json=payload)

    # Assert successful status code
    assert response.status_code == 200

    # Assert the returned JSON matches our mocked response
    data = response.json()
    assert "steps" in data
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "Check Status"
