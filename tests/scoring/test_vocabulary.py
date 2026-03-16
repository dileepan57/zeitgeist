"""
Tests for vocabulary fragmentation detector.
Covers: fragmentation scores, dominant term detection, empty input, edge cases.
"""
import pytest
from pipeline.scoring.vocabulary import compute_fragmentation, extract_variants_from_signals


class TestComputeFragmentation:

    def test_empty_variants_returns_zero(self):
        result = compute_fragmentation([])
        assert result["fragmentation_score"] == 0.0
        assert result["dominant_term"] is None
        assert result["variant_count"] == 0

    def test_single_term_low_fragmentation(self):
        """Only one term → maximum dominance → minimum fragmentation."""
        variants = ["AI tools"] * 20
        result = compute_fragmentation(variants)
        assert result["fragmentation_score"] < 0.3
        assert result["dominant_term"] == "AI tools"

    def test_all_different_terms_high_fragmentation(self):
        """30 unique terms with no repetition → maximum fragmentation."""
        variants = [f"term_{i}" for i in range(30)]
        result = compute_fragmentation(variants)
        assert result["fragmentation_score"] > 0.7

    def test_slightly_dominant_term_moderate_fragmentation(self):
        """One term appears 3x out of 15 (20% dominance) → moderate."""
        variants = ["main term"] * 3 + [f"variant_{i}" for i in range(12)]
        result = compute_fragmentation(variants)
        assert 0.4 <= result["fragmentation_score"] <= 0.9

    def test_dominant_term_identified_correctly(self):
        variants = ["sourdough bread"] * 5 + ["sourdough"] * 2 + ["artisan bread"] * 1
        result = compute_fragmentation(variants)
        assert result["dominant_term"] == "sourdough bread"

    def test_variant_count_is_unique_count(self):
        variants = ["a", "b", "c", "a", "b"]  # 3 unique
        result = compute_fragmentation(variants)
        assert result["variant_count"] == 3

    def test_fragmentation_bounded_0_to_1(self):
        for n in [1, 5, 10, 50]:
            variants = [f"term_{i}" for i in range(n)]
            result = compute_fragmentation(variants)
            assert 0.0 <= result["fragmentation_score"] <= 1.0

    def test_high_fragmentation_interpretation(self):
        variants = [f"unique_term_{i}" for i in range(25)]
        result = compute_fragmentation(variants)
        assert "unmapped" in result["interpretation"].lower() or "fragmentation" in result["interpretation"].lower()

    def test_low_fragmentation_interpretation(self):
        variants = ["AI agent"] * 20
        result = compute_fragmentation(variants)
        assert "dominant" in result["interpretation"].lower() or "low" in result["interpretation"].lower()


class TestExtractVariants:

    def test_substring_match_included(self):
        variants = extract_variants_from_signals(
            "pilates",
            ["pilates class", "pilates body", "yoga and pilates", "running shoes"]
        )
        assert "pilates class" in variants
        assert "pilates body" in variants
        assert "yoga and pilates" in variants
        assert "running shoes" not in variants

    def test_exact_topic_match_included(self):
        variants = extract_variants_from_signals("pilates", ["pilates", "yoga"])
        assert "pilates" in variants

    def test_no_match_returns_empty(self):
        variants = extract_variants_from_signals("pilates", ["yoga", "running", "cycling"])
        assert variants == []

    def test_case_insensitive_matching(self):
        variants = extract_variants_from_signals("pilates", ["PILATES class"])
        assert len(variants) > 0

    def test_word_overlap_match(self):
        """2+ words in common should match."""
        variants = extract_variants_from_signals(
            "longevity protocol",
            ["longevity protocol guide", "how to follow the longevity protocol", "other topic"]
        )
        assert "longevity protocol guide" in variants
        assert "other topic" not in variants
