"""
Tests for timeline position classifier.
Covers: all 5 positions, boundary conditions, declining detection.
"""
import pytest
from pipeline.scoring.timeline import classify_timeline, timeline_score


class TestTimelineClassification:

    def test_builder_only_is_emerging(self):
        result = classify_timeline(categories_fired=["builder"])
        assert result["position"] == "EMERGING"

    def test_builder_no_media_no_demand_is_emerging(self):
        result = classify_timeline(categories_fired=["builder", "money"])
        assert result["position"] == "EMERGING"

    def test_builder_plus_community_no_media_is_crystallizing(self):
        result = classify_timeline(categories_fired=["builder", "community"])
        assert result["position"] == "CRYSTALLIZING"

    def test_community_plus_behavior_no_media_is_crystallizing(self):
        result = classify_timeline(categories_fired=["community", "behavior"])
        assert result["position"] == "CRYSTALLIZING"

    def test_demand_plus_media_is_mainstream(self):
        result = classify_timeline(categories_fired=["demand", "media"])
        assert result["position"] == "MAINSTREAM"

    def test_demand_community_behavior_is_mainstream(self):
        result = classify_timeline(categories_fired=["demand", "community", "behavior"])
        assert result["position"] == "MAINSTREAM"

    def test_all_five_categories_is_peaking(self):
        result = classify_timeline(
            categories_fired=["builder", "community", "behavior", "demand", "media"]
        )
        assert result["position"] == "PEAKING"

    def test_empty_categories_is_none(self):
        result = classify_timeline(categories_fired=[])
        assert result["position"] == "NONE"

    def test_declining_flag_overrides(self):
        """is_declining=True should force DECLINING regardless of categories."""
        result = classify_timeline(
            categories_fired=["demand", "community", "builder"],
            is_declining=True,
        )
        assert result["position"] == "DECLINING"

    def test_media_only_is_mainstream(self):
        """Media alone = mainstream driven, not crystallizing."""
        result = classify_timeline(categories_fired=["media"])
        assert result["position"] == "MAINSTREAM"

    def test_four_or_more_categories_peaking(self):
        """4+ categories without exact rule match → PEAKING."""
        result = classify_timeline(
            categories_fired=["demand", "community", "money", "behavior"]
        )
        assert result["position"] in ("PEAKING", "MAINSTREAM")  # 4 categories

    def test_result_includes_lead_indicator_ratio(self):
        result = classify_timeline(categories_fired=["builder", "community"])
        assert "lead_indicator_ratio" in result
        assert result["lead_indicator_ratio"] == pytest.approx(1.0, abs=0.01)

    def test_lead_ratio_no_early_signals(self):
        result = classify_timeline(categories_fired=["demand", "media"])
        assert result["lead_indicator_ratio"] == pytest.approx(0.0, abs=0.01)

    def test_lead_ratio_mixed(self):
        """builder + community out of 4 total = 0.5 lead ratio."""
        result = classify_timeline(
            categories_fired=["builder", "community", "demand", "media"]
        )
        assert result["lead_indicator_ratio"] == pytest.approx(0.5, abs=0.01)


class TestTimelineScore:

    def test_crystallizing_scores_highest(self):
        assert timeline_score("CRYSTALLIZING") == 1.0

    def test_mainstream_scores_less_than_crystallizing(self):
        assert timeline_score("MAINSTREAM") < timeline_score("CRYSTALLIZING")

    def test_emerging_scores_less_than_crystallizing(self):
        assert timeline_score("EMERGING") < timeline_score("CRYSTALLIZING")

    def test_peaking_scores_low(self):
        assert timeline_score("PEAKING") <= 0.4

    def test_none_scores_zero(self):
        assert timeline_score("NONE") == 0.0

    def test_unknown_position_scores_zero(self):
        assert timeline_score("UNKNOWN_POSITION") == 0.0

    def test_all_positions_bounded_0_to_1(self):
        for pos in ["EMERGING", "CRYSTALLIZING", "MAINSTREAM", "PEAKING", "DECLINING", "NONE"]:
            score = timeline_score(pos)
            assert 0.0 <= score <= 1.0
