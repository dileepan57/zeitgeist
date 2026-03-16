"""
Tests for signal independence scorer.
Covers: echo chain detection, category deduplication, single-source, multi-category.
"""
import pytest
from datetime import datetime, timedelta
from pipeline.scoring.independence import score_independence
from tests.conftest import make_signal, make_echo_cascade


class TestBasicIndependence:

    def test_empty_signals_returns_zero(self):
        result = score_independence([])
        assert result["independence_score"] == 0.0
        assert result["categories_fired"] == []
        assert result["echo_detected"] is False

    def test_no_fired_signals_returns_zero(self):
        signals = [make_signal(fired=False), make_signal(fired=False)]
        result = score_independence(signals)
        assert result["independence_score"] == 0.0

    def test_single_source_scores_one_sixth(self):
        signals = [make_signal(source="reddit", category="community", fired=True)]
        result = score_independence(signals)
        assert result["independence_score"] == pytest.approx(1/6, abs=0.01)
        assert result["categories_fired"] == ["community"]

    def test_two_independent_categories(self):
        signals = [
            make_signal(source="reddit", category="community", fired=True),
            make_signal(source="github_trending", category="builder", fired=True),
        ]
        result = score_independence(signals)
        assert result["independence_score"] == pytest.approx(2/6, abs=0.01)

    def test_all_six_categories_scores_one(self):
        signals = [
            make_signal(source="gdelt", category="media", fired=True),
            make_signal(source="google_trends", category="demand", fired=True),
            make_signal(source="app_store", category="behavior", fired=True),
            make_signal(source="github_trending", category="builder", fired=True),
            make_signal(source="reddit", category="community", fired=True),
            make_signal(source="crunchbase", category="money", fired=True),
        ]
        result = score_independence(signals)
        assert result["independence_score"] == pytest.approx(1.0, abs=0.01)

    def test_multiple_sources_same_category_counts_once(self):
        """Two media sources should still count as 1 category."""
        signals = [
            make_signal(source="gdelt", category="media", fired=True),
            make_signal(source="youtube", category="media", fired=True),
            make_signal(source="substack", category="media", fired=True),
        ]
        result = score_independence(signals)
        assert result["independence_score"] == pytest.approx(1/6, abs=0.01)
        assert len(result["categories_fired"]) == 1


class TestEchoDetection:

    def test_media_then_demand_within_48h_detected_as_echo(self):
        now = datetime.utcnow()
        signals = [
            make_signal(
                source="gdelt", category="media", fired=True,
                created_at=(now - timedelta(hours=36)).isoformat(),
            ),
            make_signal(
                source="google_trends", category="demand", fired=True,
                created_at=now.isoformat(),
            ),
        ]
        result = score_independence(signals)
        assert result["echo_detected"] is True
        # Demand should be removed from adjusted categories
        assert "demand" not in result["adjusted_categories"]
        # Only media counts
        assert "media" in result["adjusted_categories"]

    def test_media_then_community_within_48h_detected_as_echo(self):
        now = datetime.utcnow()
        signals = [
            make_signal(
                source="gdelt", category="media", fired=True,
                created_at=(now - timedelta(hours=12)).isoformat(),
            ),
            make_signal(
                source="reddit", category="community", fired=True,
                created_at=now.isoformat(),
            ),
        ]
        result = score_independence(signals)
        assert result["echo_detected"] is True
        assert "community" not in result["adjusted_categories"]

    def test_media_then_demand_beyond_48h_not_echo(self):
        """If demand fires >48h after media, it's not an echo — independent signal."""
        now = datetime.utcnow()
        signals = [
            make_signal(
                source="gdelt", category="media", fired=True,
                created_at=(now - timedelta(hours=72)).isoformat(),
            ),
            make_signal(
                source="google_trends", category="demand", fired=True,
                created_at=now.isoformat(),
            ),
        ]
        result = score_independence(signals)
        # Beyond 48h window — should not be treated as echo
        assert result["echo_detected"] is False
        assert "demand" in result["adjusted_categories"]

    def test_no_timestamps_no_echo_detection(self):
        """Without timestamps, echo detection cannot fire."""
        signals = [
            make_signal(source="gdelt", category="media", fired=True),
            make_signal(source="google_trends", category="demand", fired=True),
        ]
        # No timestamps → echo detection skips, both categories count
        result = score_independence(signals)
        assert result["echo_detected"] is False

    def test_builder_plus_demand_not_echo(self):
        """Builder → demand is not an echo pair — independent."""
        signals = [
            make_signal(source="github_trending", category="builder", fired=True),
            make_signal(source="google_trends", category="demand", fired=True),
        ]
        result = score_independence(signals)
        assert result["echo_detected"] is False
        assert len(result["adjusted_categories"]) == 2

    def test_echo_reduces_independence_score(self):
        """With echo, independence_score should be lower than without."""
        now = datetime.utcnow()
        with_echo = [
            make_signal(source="gdelt", category="media", fired=True,
                        created_at=(now - timedelta(hours=20)).isoformat()),
            make_signal(source="google_trends", category="demand", fired=True,
                        created_at=now.isoformat()),
        ]
        without_echo = [
            make_signal(source="gdelt", category="media", fired=True),
            make_signal(source="github_trending", category="builder", fired=True),
        ]
        echo_result = score_independence(with_echo)
        no_echo_result = score_independence(without_echo)
        assert echo_result["independence_score"] < no_echo_result["independence_score"]
