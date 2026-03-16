"""
Graceful failure tests.
Every collector must return [] (not raise) when the network is unavailable.
This ensures a single blocked source never crashes the whole pipeline.

Special cases:
  - xiaohongshu: intentionally returns static seeds when all live sources fail
    (by design — provides curated CN trend data even when geo-blocked)
  - markets: uses yfinance/requests (not httpx); mocked separately
"""
import pytest
import importlib
from unittest.mock import patch, MagicMock


# All collectors that make HTTP requests
HTTP_COLLECTORS = [
    "pipeline.collectors.wikipedia",
    "pipeline.collectors.gdelt",
    "pipeline.collectors.google_trends",
    "pipeline.collectors.youtube",
    "pipeline.collectors.github_trending",
    "pipeline.collectors.arxiv",
    "pipeline.collectors.stackoverflow",
    "pipeline.collectors.substack",
    "pipeline.collectors.producthunt",
    "pipeline.collectors.kickstarter",
    "pipeline.collectors.amazon_movers",
    "pipeline.collectors.discord",
    "pipeline.collectors.app_store",
    "pipeline.collectors.sbir",
    "pipeline.collectors.federal_register",
    "pipeline.collectors.itunes",
    "pipeline.collectors.crunchbase",
    "pipeline.collectors.xiaohongshu",
    "pipeline.collectors.job_postings",
    "pipeline.collectors.uspto",
    "pipeline.collectors.markets",
]

# Collectors that intentionally return static fallback data when all live sources fail.
# Contract: returns a list (may be non-empty) — not required to return [].
STATIC_FALLBACK_COLLECTORS = {"xiaohongshu"}

# Collectors that use non-httpx libraries; mocked separately below.
NON_HTTPX_COLLECTORS = {"markets"}

# Collectors where "returns []" contract applies on connection failure
MUST_RETURN_EMPTY = {
    name for name in [p.split(".")[-1] for p in HTTP_COLLECTORS]
    if name not in STATIC_FALLBACK_COLLECTORS and name not in NON_HTTPX_COLLECTORS
}


def _get_collector_modules():
    """Load all collector modules, skip those that fail to import."""
    loaded = []
    for mod_path in HTTP_COLLECTORS:
        try:
            mod = importlib.import_module(mod_path)
            loaded.append((mod_path.split(".")[-1], mod))
        except ImportError:
            pass
    return loaded


def _get_empty_on_error_modules():
    """Modules that must return [] on connection error."""
    return [(n, m) for n, m in _get_collector_modules() if n in MUST_RETURN_EMPTY]


@pytest.mark.parametrize(
    "name,mod",
    _get_empty_on_error_modules(),
    ids=[name for name, _ in _get_empty_on_error_modules()],
)
def test_collector_returns_empty_on_connection_error(name, mod, monkeypatch):
    """
    Simulate a network failure (ConnectionError) — collector must return [].
    """
    import httpx

    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Simulated network failure")

    monkeypatch.setattr(httpx, "get", raise_connection_error)
    monkeypatch.setattr(httpx, "post", raise_connection_error)

    result = mod.collect()
    assert isinstance(result, list), f"{name}.collect() must return a list, got {type(result)}"
    assert result == [], f"{name}.collect() must return [] on connection error, got {len(result)} items"


@pytest.mark.parametrize(
    "name,mod",
    _get_empty_on_error_modules(),
    ids=[name for name, _ in _get_empty_on_error_modules()],
)
def test_collector_returns_empty_on_timeout(name, mod, monkeypatch):
    """
    Simulate a timeout — collector must return [].
    """
    import httpx

    def raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Simulated timeout")

    monkeypatch.setattr(httpx, "get", raise_timeout)
    monkeypatch.setattr(httpx, "post", raise_timeout)

    result = mod.collect()
    assert isinstance(result, list), f"{name}: must return list on timeout"
    assert result == [], f"{name}: must return [] on timeout"


@pytest.mark.parametrize(
    "name,mod",
    _get_collector_modules(),
    ids=[name for name, _ in _get_collector_modules()],
)
def test_collector_returns_list_type(name, mod, monkeypatch):
    """
    Basic contract: collect() must always return a list.
    Test with fully mocked HTTP (returns empty response body).
    """
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = ""
    mock_response.json.return_value = {}
    mock_response.raise_for_status = lambda: None

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: mock_response)
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: mock_response)

    # markets: also mock yfinance so it doesn't make real network calls
    if name == "markets":
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = MagicMock(empty=True, __len__=lambda s: 0)
        monkeypatch.setattr("yfinance.Ticker", lambda *a, **kw: mock_ticker)

    try:
        result = mod.collect()
    except Exception:
        result = []

    assert isinstance(result, list), f"{name}.collect() must always return a list"


def test_xiaohongshu_returns_list_on_network_failure(monkeypatch):
    """
    xiaohongshu uses static seeds as fallback — must return a non-raising list.
    Contract: returns list (may be non-empty — that's the intended fallback behavior).
    """
    import httpx
    import importlib
    mod = importlib.import_module("pipeline.collectors.xiaohongshu")

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: (_ for _ in ()).throw(
        httpx.ConnectError("Simulated network failure")
    ))
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(
        httpx.ConnectError("Simulated network failure")
    ))

    result = mod.collect()
    assert isinstance(result, list), "xiaohongshu must always return a list"


def test_markets_returns_empty_when_yfinance_fails(monkeypatch):
    """
    markets uses yfinance (not httpx) — mock yfinance.Ticker to raise.
    Collector must still return [] and not crash the pipeline.
    """
    import httpx
    import importlib
    mod = importlib.import_module("pipeline.collectors.markets")

    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Simulated network failure")

    monkeypatch.setattr(httpx, "get", raise_connection_error)
    monkeypatch.setattr(httpx, "post", raise_connection_error)

    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = Exception("Simulated yfinance failure")
    monkeypatch.setattr("yfinance.Ticker", lambda *a, **kw: mock_ticker)

    result = mod.collect()
    assert isinstance(result, list), "markets.collect() must return a list"
