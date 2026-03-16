"""
Shared test fixtures for the Zeitgeist test suite.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ── Signal factories ────────────────────────────────────────────

def make_signal(
    topic="test_topic",
    source="reddit",
    category="community",
    spike_score=0.8,
    fired=True,
    raw_value=100,
    baseline_value=50,
    timestamp=None,
    **extra,
) -> dict:
    """Create a minimal valid signal dict."""
    return {
        "topic": topic,
        "signal_source": source,
        "signal_category": category,
        "spike_score": spike_score,
        "fired": fired,
        "raw_value": raw_value,
        "baseline_value": baseline_value,
        "timestamp": timestamp or datetime.utcnow().isoformat(),
        **extra,
    }


def make_signals_for_categories(*categories: str, topic="test_topic") -> list[dict]:
    """
    Create one fired signal per category.
    categories: subset of ['media', 'demand', 'behavior', 'builder', 'community', 'money']
    """
    CAT_TO_SOURCE = {
        "media": "gdelt",
        "demand": "google_trends",
        "behavior": "app_store",
        "builder": "github_trending",
        "community": "reddit",
        "money": "crunchbase",
    }
    return [
        make_signal(topic=topic, source=CAT_TO_SOURCE[cat], category=cat)
        for cat in categories
    ]


def make_echo_cascade(topic="echo_test", delay_hours_1=24, delay_hours_2=48) -> list[dict]:
    """
    Simulate a media cascade: news fires → demand spike → community spike.
    Used to test echo detection logic.
    """
    now = datetime.utcnow()
    return [
        make_signal(
            topic=topic, source="gdelt", category="media",
            timestamp=(now - timedelta(hours=delay_hours_2)).isoformat(),
        ),
        make_signal(
            topic=topic, source="google_trends", category="demand",
            timestamp=(now - timedelta(hours=delay_hours_1)).isoformat(),
        ),
        make_signal(
            topic=topic, source="reddit", category="community",
            timestamp=now.isoformat(),
        ),
    ]


# ── DB mock ──────────────────────────────────────────────────────

@pytest.fixture
def mock_db(monkeypatch):
    """
    Patch pipeline.utils.db so tests don't touch Supabase.
    Returns a mock that records calls.
    """
    mock = MagicMock()
    mock.select.return_value = []
    mock.insert.return_value = [{"id": "test-uuid-123"}]
    mock.upsert.return_value = [{"id": "test-uuid-123"}]
    mock.update.return_value = [{"id": "test-uuid-123"}]
    mock.get_client.return_value = MagicMock()

    monkeypatch.setattr("pipeline.utils.db.select", mock.select)
    monkeypatch.setattr("pipeline.utils.db.insert", mock.insert)
    monkeypatch.setattr("pipeline.utils.db.upsert", mock.upsert)
    monkeypatch.setattr("pipeline.utils.db.update", mock.update)
    monkeypatch.setattr("pipeline.utils.db.get_client", mock.get_client)
    return mock


# ── Claude mock ──────────────────────────────────────────────────

@pytest.fixture
def mock_claude(monkeypatch):
    """
    Patch the Claude API client so tests don't make real API calls.
    Returns a dict with a 'response_text' field you can set per-test.
    """
    state = {"response_text": "Test gap analysis output."}

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=state["response_text"])]
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    def get_client_mock():
        return mock_client

    monkeypatch.setattr("pipeline.synthesis.claude.get_client", get_client_mock)
    return {"client": mock_client, "response": mock_response, "state": state}


# ── Telemetry mock ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def suppress_telemetry(monkeypatch):
    """
    Suppress all telemetry writes in tests so they don't need a DB connection.
    Applied automatically to all tests.
    """
    monkeypatch.setattr(
        "pipeline.telemetry.store.flush_collector_run",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "pipeline.telemetry.store.flush_claude_usage",
        lambda **kwargs: None,
    )
