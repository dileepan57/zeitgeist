"""
Tests for the full scoring engine pipeline.
Covers: end-to-end synthetic signal processing, edge cases, robustness.
"""
import pytest
from unittest.mock import patch, MagicMock
from pipeline.scoring.engine import run as engine_run
from tests.conftest import make_signal, make_signals_for_categories


class TestEngineEndToEnd:

    def _patch_entities(self, monkeypatch):
        """Patch entity resolution to return the topic as-is."""
        monkeypatch.setattr(
            "pipeline.scoring.engine.resolve_topic",
            lambda t: t,
        )

    def test_empty_signals_returns_empty(self, monkeypatch):
        self._patch_entities(monkeypatch)
        result = engine_run([])
        assert result == []

    def test_single_signal_produces_scored_topic(self, monkeypatch):
        self._patch_entities(monkeypatch)
        signals = [make_signal(topic="test_topic", source="reddit", category="community")]
        result = engine_run(signals)
        assert len(result) == 1
        assert result[0]["topic"] == "test_topic"
        assert "opportunity_score" in result[0]
        assert 0.0 <= result[0]["opportunity_score"] <= 1.0

    def test_results_sorted_by_opportunity_score_desc(self, monkeypatch):
        self._patch_entities(monkeypatch)
        # Topic A: builder+community+demand (should score higher)
        topic_a = make_signals_for_categories("builder", "community", "demand", topic="topic_a")
        # Topic B: just media
        topic_b = [make_signal(topic="topic_b", source="gdelt", category="media")]
        result = engine_run(topic_a + topic_b)
        scores = [r["opportunity_score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_topics_grouped_by_canonical_name(self, monkeypatch):
        """Signals with the same canonical topic should be grouped."""
        monkeypatch.setattr("pipeline.scoring.engine.resolve_topic", lambda t: "unified_topic")
        signals = [
            make_signal(topic="variant_a", source="reddit", category="community"),
            make_signal(topic="variant_b", source="github_trending", category="builder"),
        ]
        result = engine_run(signals)
        # All signals grouped under one canonical topic
        assert len(result) == 1
        assert result[0]["topic"] == "unified_topic"

    def test_missing_fired_field_defaults_to_false(self, monkeypatch):
        self._patch_entities(monkeypatch)
        signal = make_signal(topic="test_topic", source="reddit", category="community")
        del signal["fired"]  # Remove fired field
        result = engine_run([signal])
        # Should not raise; fired defaults to False
        assert len(result) == 1

    def test_chinese_unicode_topic_no_exception(self, monkeypatch):
        """Chinese topic names from Xiaohongshu should be handled gracefully."""
        self._patch_entities(monkeypatch)
        signals = [
            make_signal(topic="美妆", source="xiaohongshu", category="demand", spike_score=0.9),
        ]
        result = engine_run(signals)
        assert len(result) == 1
        assert result[0]["topic"] == "美妆"

    def test_all_required_score_fields_present(self, monkeypatch):
        self._patch_entities(monkeypatch)
        signals = make_signals_for_categories("community", "demand")
        result = engine_run(signals)
        assert len(result) > 0
        topic = result[0]
        required_fields = [
            "topic", "opportunity_score", "independence_score", "actionability_score",
            "timeline_position", "vocabulary_fragmentation", "lead_indicator_ratio",
            "categories_fired", "sources_fired", "echo_detected",
        ]
        for field in required_fields:
            assert field in topic, f"Missing field: {field}"

    def test_evergreen_suppressed_topic_scores_zero(self, monkeypatch):
        """Evergreen topic with weak spike should be suppressed to 0."""
        self._patch_entities(monkeypatch)
        signals = [
            # Weak spike on evergreen topic
            make_signal(topic="artificial intelligence", source="google_trends",
                        category="demand", spike_score=1.5, fired=True),
        ]
        result = engine_run(signals)
        if result:
            # Should be suppressed or very low score
            assert result[0]["opportunity_score"] == 0.0 or result[0]["timeline_position"] == "NONE"

    def test_full_signal_convergence_scores_high(self, monkeypatch):
        """All 6 categories firing should produce the highest possible score."""
        self._patch_entities(monkeypatch)
        signals = make_signals_for_categories(
            "media", "demand", "behavior", "builder", "community", "money",
            topic="viral_trend",
        )
        # Add high spike scores
        for s in signals:
            s["spike_score"] = 5.0
        result = engine_run(signals)
        assert len(result) == 1
        assert result[0]["opportunity_score"] > 0.3  # Should be meaningfully above zero

    def test_multiple_topics_all_scored(self, monkeypatch):
        self._patch_entities(monkeypatch)
        signals = []
        for i in range(5):
            signals.append(make_signal(
                topic=f"topic_{i}",
                source="reddit",
                category="community",
                spike_score=0.5 + i * 0.1,
            ))
        result = engine_run(signals)
        assert len(result) == 5

    def test_malformed_signal_dict_handled_gracefully(self, monkeypatch):
        """Signals with missing keys should not crash the engine."""
        self._patch_entities(monkeypatch)
        signals = [
            {"topic": "test_topic"},  # Minimal signal, many fields missing
            make_signal(topic="test_topic", source="reddit", category="community"),
        ]
        # Should not raise
        result = engine_run(signals)
        assert isinstance(result, list)
