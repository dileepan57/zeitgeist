"""
Collector test fixtures: mock HTTP responses via respx.
"""
import pytest
import respx
import httpx


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make time.sleep a no-op so retry backoff doesn't slow tests."""
    import pipeline.utils.rate_limiter as rl
    monkeypatch.setattr(rl, "_sleep", lambda s: None, raising=False)
    # Patch time.sleep globally for collector tests
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


@pytest.fixture
def mock_httpx():
    """
    Context manager that intercepts all httpx requests.
    Use within test functions: `with respx.mock() as mock: ...`
    """
    return respx


@pytest.fixture
def wikipedia_html():
    """Minimal Wikipedia API response."""
    return {
        "items": [
            {
                "articles": [
                    {"article": "Python_(programming_language)", "views": 50000},
                    {"article": "Machine_learning", "views": 45000},
                    {"article": "ChatGPT", "views": 80000},
                    {"article": "Main_Page", "views": 5000000},  # Should be filtered
                ]
            }
        ]
    }


@pytest.fixture
def reddit_posts():
    """Minimal Reddit API response."""
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "I wish there was an app for tracking AI tools",
                        "score": 1500,
                        "num_comments": 200,
                        "selftext": "Why doesn't anyone build this?",
                    }
                },
                {
                    "data": {
                        "title": "Best productivity apps 2024",
                        "score": 800,
                        "num_comments": 50,
                        "selftext": "",
                    }
                },
            ]
        }
    }


@pytest.fixture
def gdelt_response():
    """Minimal GDELT API response."""
    return {
        "articles": [
            {"title": "AI agents transforming work", "url": "https://example.com/1"},
            {"title": "Machine learning in healthcare", "url": "https://example.com/2"},
        ]
    }
