"""
Tests for actionability scorer (demand × frustration × supply_gap).
Covers: zero-product edge cases, frustration signals, supply gap signals.
"""
import pytest
from pipeline.scoring.actionability import (
    compute_actionability,
    score_demand,
    score_frustration,
    score_supply_gap,
)
from tests.conftest import make_signal


class TestDemandScoring:

    def test_no_demand_signals_returns_zero(self):
        # Only builder signals, no demand/community sources
        signals = [make_signal(source="github_trending", category="builder", fired=True, spike_score=0.9)]
        assert score_demand(signals) == 0.0

    def test_unfired_demand_signals_not_counted(self):
        signals = [make_signal(source="google_trends", fired=False, spike_score=0.9)]
        assert score_demand(signals) == 0.0

    def test_single_demand_signal(self):
        signals = [make_signal(source="google_trends", fired=True, spike_score=0.8)]
        score = score_demand(signals)
        assert score == pytest.approx(0.8, abs=0.01)

    def test_multiple_demand_signals_averaged(self):
        signals = [
            make_signal(source="google_trends", fired=True, spike_score=0.6),
            make_signal(source="reddit", fired=True, spike_score=1.0),
        ]
        score = score_demand(signals)
        # Capped at 1.0 each, averaged: (0.6 + 1.0) / 2 = 0.8
        assert score == pytest.approx(0.8, abs=0.01)

    def test_spike_score_capped_at_1(self):
        """Spike scores > 1 should be capped at 1.0 for demand."""
        signals = [make_signal(source="google_trends", fired=True, spike_score=5.0)]
        score = score_demand(signals)
        assert score <= 1.0


class TestFrustrationScoring:

    def test_no_frustration_signals_returns_default(self):
        """No explicit frustration signals → small default (0.2)."""
        signals = [make_signal(source="github_trending", fired=True)]
        score = score_frustration(signals)
        assert score == pytest.approx(0.2, abs=0.01)

    def test_reddit_frustration_signal(self):
        signals = [
            make_signal(source="reddit", fired=True, frustration_signal=True),
        ]
        score = score_frustration(signals)
        assert score > 0.5

    def test_gdelt_negative_tone_boosts_frustration(self):
        signals = [
            make_signal(source="gdelt", fired=True, avg_tone=-5.0),
        ]
        score = score_frustration(signals)
        assert score > 0.2

    def test_app_store_low_rating_boosts_frustration(self):
        # avg_rating=1.5 → (3.5-1.5)/3.5 ≈ 0.57, clearly above the 0.2 default
        signals = [
            make_signal(source="app_store", fired=True, avg_rating=1.5),
        ]
        score = score_frustration(signals)
        assert score > 0.2

    def test_app_store_high_rating_no_boost(self):
        signals = [
            make_signal(source="app_store", fired=True, avg_rating=4.8),
        ]
        score = score_frustration(signals)
        assert score == pytest.approx(0.2, abs=0.01)  # No frustration signals → default

    def test_frustration_bounded_0_to_1(self):
        signals = [
            make_signal(source="reddit", fired=True, frustration_signal=True),
            make_signal(source="gdelt", fired=True, avg_tone=-50.0),
            make_signal(source="app_store", fired=True, avg_rating=1.0),
        ]
        score = score_frustration(signals)
        assert 0.0 <= score <= 1.0


class TestSupplyGapScoring:

    def test_no_supply_signals_returns_moderate_default(self):
        signals = [make_signal(source="reddit", fired=True)]
        score = score_supply_gap(signals)
        assert score == pytest.approx(0.4, abs=0.01)

    def test_few_github_repos_high_gap(self):
        signals = [make_signal(source="github_trending", fired=True, raw_value=2)]
        score = score_supply_gap(signals)
        assert score > 0.7

    def test_many_github_repos_low_gap(self):
        signals = [make_signal(source="github_trending", fired=True, raw_value=50)]
        score = score_supply_gap(signals)
        assert score < 0.5

    def test_zero_producthunt_launches_max_gap(self):
        signals = [make_signal(source="producthunt", fired=True, raw_value=0)]
        score = score_supply_gap(signals)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_crunchbase_no_funding_high_gap(self):
        signals = [make_signal(source="crunchbase", fired=True, raw_value=0)]
        score = score_supply_gap(signals)
        assert score > 0.7

    def test_app_store_few_apps_high_gap(self):
        signals = [make_signal(source="app_store", fired=True, raw_value=2, avg_rating=4.0)]
        score = score_supply_gap(signals)
        assert score > 0.7


class TestCompositeActionability:

    def test_zero_demand_produces_zero_composite(self):
        """Multiplicative formula: if demand=0, composite must be 0."""
        signals = [
            make_signal(source="github_trending", category="builder", fired=True, spike_score=0.9),
        ]
        result = compute_actionability(signals)
        assert result["demand_score"] == 0.0
        assert result["actionability_score"] == 0.0

    def test_all_three_factors_present_nonzero(self):
        signals = [
            make_signal(source="google_trends", category="demand", fired=True, spike_score=0.7),
            make_signal(source="reddit", category="community", fired=True, frustration_signal=True),
            make_signal(source="github_trending", category="builder", fired=True, raw_value=3),
        ]
        result = compute_actionability(signals)
        assert result["actionability_score"] > 0.0

    def test_high_frustration_boosts_composite(self):
        """frustration > 0.7 gets a 1.3x boost."""
        signals_low = [
            make_signal(source="google_trends", fired=True, spike_score=0.8),
            make_signal(source="reddit", fired=True, frustration_signal=False),
        ]
        signals_high = [
            make_signal(source="google_trends", fired=True, spike_score=0.8),
            make_signal(source="reddit", fired=True, frustration_signal=True),
            make_signal(source="gdelt", fired=True, avg_tone=-8.0),
        ]
        low = compute_actionability(signals_low)
        high = compute_actionability(signals_high)
        # High frustration should produce higher or equal actionability
        assert high["actionability_score"] >= low["actionability_score"]

    def test_actionability_bounded_0_to_1(self):
        signals = [
            make_signal(source="google_trends", fired=True, spike_score=1.0),
            make_signal(source="reddit", fired=True, frustration_signal=True),
            make_signal(source="producthunt", fired=True, raw_value=0),
        ]
        result = compute_actionability(signals)
        assert 0.0 <= result["actionability_score"] <= 1.0

    def test_returns_all_sub_scores(self):
        signals = [make_signal(source="google_trends", fired=True, spike_score=0.5)]
        result = compute_actionability(signals)
        assert "demand_score" in result
        assert "frustration_score" in result
        assert "supply_gap_score" in result
        assert "actionability_score" in result
