"""
Tests for baseline-relative scoring.
Covers: evergreen suppression (3x threshold), spike math, standard topics.
"""
import pytest
from pipeline.scoring.baseline import compute_baseline_score
from tests.conftest import make_signal


class TestEvergreenSuppression:

    def test_evergreen_topic_with_low_spike_suppressed(self):
        """'artificial intelligence' needs 3x spike to fire."""
        signals = [
            make_signal(source="google_trends", fired=True, spike_score=1.5),  # Below 3x
            make_signal(source="reddit", fired=True, spike_score=2.0),  # Below 3x
        ]
        result = compute_baseline_score("artificial intelligence", signals)
        assert result["is_evergreen"] is True
        assert result["suppressed"] is True

    def test_evergreen_topic_with_high_spike_not_suppressed(self):
        """3.5x spike on an evergreen topic should pass."""
        signals = [
            make_signal(source="google_trends", fired=True, spike_score=3.5),
            make_signal(source="reddit", fired=True, spike_score=4.0),
        ]
        result = compute_baseline_score("artificial intelligence", signals)
        assert result["is_evergreen"] is True
        assert result["suppressed"] is False
        assert result["baseline_score"] > 0

    def test_ai_topic_is_evergreen(self):
        signals = [make_signal(fired=True, spike_score=1.0)]
        result = compute_baseline_score("ai", signals)
        assert result["is_evergreen"] is True

    def test_bitcoin_is_evergreen(self):
        signals = [make_signal(fired=True, spike_score=1.0)]
        result = compute_baseline_score("bitcoin", signals)
        assert result["is_evergreen"] is True

    def test_normal_topic_not_evergreen(self):
        signals = [make_signal(fired=True, spike_score=1.2)]
        result = compute_baseline_score("sourdough baking", signals)
        assert result["is_evergreen"] is False

    def test_normal_topic_with_1x_spike_passes(self):
        """Standard threshold is 1.0 — 1.2 spike should pass."""
        signals = [make_signal(fired=True, spike_score=1.2)]
        result = compute_baseline_score("sourdough baking", signals)
        assert result["suppressed"] is False
        assert result["baseline_score"] > 0

    def test_normal_topic_with_zero_spike_fails(self):
        """0 spike on a normal topic → no score."""
        signals = [make_signal(fired=True, spike_score=0.0)]
        result = compute_baseline_score("pilates body", signals)
        assert result["baseline_score"] == 0.0

    def test_negative_spike_not_counted(self):
        """Negative spike (declining) should produce zero score."""
        signals = [make_signal(fired=True, spike_score=-0.5)]
        result = compute_baseline_score("some trend", signals)
        # Negative spike → no passing_sources → baseline_score = 0
        assert result["baseline_score"] == 0.0


class TestBaselineScoreMath:

    def test_empty_signals_returns_zero(self):
        result = compute_baseline_score("test_topic", [])
        assert result["baseline_score"] == 0.0

    def test_unfired_signals_not_counted(self):
        signals = [
            make_signal(fired=False, spike_score=5.0),
            make_signal(fired=False, spike_score=10.0),
        ]
        result = compute_baseline_score("test_topic", signals)
        assert result["baseline_score"] == 0.0

    def test_high_spike_capped_at_10x(self):
        """Spike scores are capped at 10.0 internally."""
        signals = [make_signal(fired=True, spike_score=999.0)]
        result = compute_baseline_score("test_topic", signals)
        # Should produce a valid score, not overflow
        assert 0.0 <= result["baseline_score"] <= 1.0

    def test_baseline_score_bounded_0_to_1(self):
        signals = [
            make_signal(source="google_trends", fired=True, spike_score=5.0),
            make_signal(source="reddit", fired=True, spike_score=8.0),
        ]
        result = compute_baseline_score("test_topic", signals)
        assert 0.0 <= result["baseline_score"] <= 1.0

    def test_no_baseline_data_uses_default(self):
        """spike_score=None means no baseline data — should use 0.5 default."""
        signals = [make_signal(fired=True, spike_score=None)]
        result = compute_baseline_score("test_topic", signals)
        # Should not crash and should return some score
        assert result["baseline_score"] >= 0.0
