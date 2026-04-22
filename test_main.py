"""Comprehensive test suite for VoteVibe Election Process Education API."""
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app

test_client = TestClient(app)


def test_read_root() -> None:
    """Test that the root endpoint serves index.html successfully."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_security_headers_present() -> None:
    """Verify enterprise security headers are injected on every response."""
    response = test_client.get("/")
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert "max-age=31536000" in response.headers.get(
        "Strict-Transport-Security", ""
    )
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "strict-origin" in response.headers.get(
        "Referrer-Policy", ""
    )


def test_cache_control_get() -> None:
    """Verify Cache-Control header is set for GET requests."""
    response = test_client.get("/")
    assert "public" in response.headers.get("Cache-Control", "")


def test_election_timeline_validation_error_empty_payload() -> None:
    """Empty payload should trigger a 422 Unprocessable Entity."""
    response = test_client.post("/api/election-timeline", json={})
    assert response.status_code == 422


def test_election_timeline_validation_error_invalid_zip() -> None:
    """Invalid zip code length should trigger a 422."""
    response = test_client.post(
        "/api/election-timeline",
        json={"zip_code": "12", "query": "How to register to vote?"}
    )
    assert response.status_code == 422


def test_election_timeline_validation_error_short_query() -> None:
    """Query below min_length should trigger a 422."""
    response = test_client.post(
        "/api/election-timeline",
        json={"zip_code": "12345", "query": "ab"}
    )
    assert response.status_code == 422


def test_election_timeline_validation_error_non_numeric_zip() -> None:
    """Non-numeric but too short zip code should trigger a 422."""
    response = test_client.post(
        "/api/election-timeline",
        json={"zip_code": "ab", "query": "How do I register to vote?"}
    )
    assert response.status_code == 422


@patch("main.client")
def test_election_timeline_success(mock_client: MagicMock) -> None:
    """Test successful timeline generation with mocked Gemini client."""
    mock_response = MagicMock()
    mock_response.text = (
        '{"steps": [{"step": 1, "action": "Check Status", '
        '"details": "Verify your voter registration status online."}]}'
    )

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client.models = mock_models

    payload = {
        "zip_code": "12345",
        "query": "How do I register to vote in my county?"
    }

    response = test_client.post("/api/election-timeline", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "steps" in data
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "Check Status"


@patch("main.client")
def test_election_timeline_json_parse_error(
    mock_client: MagicMock,
) -> None:
    """Test that malformed Gemini response returns a 500."""
    mock_response = MagicMock()
    mock_response.text = "this is not valid json"

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client.models = mock_models

    payload = {
        "zip_code": "12345",
        "query": "How do I register to vote in my county?"
    }

    response = test_client.post("/api/election-timeline", json=payload)
    assert response.status_code == 500


@patch("main.client", None)
def test_election_timeline_no_client() -> None:
    """Test that missing GenAI client returns a 500."""
    payload = {
        "zip_code": "12345",
        "query": "How do I register to vote in my county?"
    }
    response = test_client.post("/api/election-timeline", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "AI Service Initializing."


def test_indian_pin_code_validation() -> None:
    """Test that 6-digit Indian PIN codes pass validation."""
    response = test_client.post(
        "/api/election-timeline",
        json={
            "zip_code": "110001",
            "query": "When is the next election in my area?"
        }
    )
    # Should not be a 422 (validation passes)
    assert response.status_code != 422


def test_cache_control_post() -> None:
    """Verify Cache-Control is no-store for POST requests."""
    response = test_client.post("/api/election-timeline", json={})
    assert "no-store" in response.headers.get("Cache-Control", "")
