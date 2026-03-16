"""
Tests for Claude synthesis layer.
Covers: mocked API calls, JSON parsing robustness, fallback handling.
"""
import pytest
import json
from unittest.mock import MagicMock, patch
from tests.conftest import make_signals_for_categories


@pytest.fixture
def sample_topic_data():
    signals = make_signals_for_categories("community", "demand", "builder")
    return {
        "topic": "pilates body",
        "opportunity_score": 0.62,
        "independence_score": 0.5,
        "actionability_score": 0.45,
        "timeline_position": "CRYSTALLIZING",
        "timeline_description": "Community forming",
        "lead_indicator_ratio": 0.67,
        "demand_score": 0.7,
        "frustration_score": 0.5,
        "supply_gap_score": 0.6,
        "vocabulary_fragmentation": 0.65,
        "variant_count": 8,
        "vocab_interpretation": "Moderate fragmentation",
        "adjusted_categories": ["community", "demand", "builder"],
        "sources_fired": ["reddit", "google_trends", "github_trending"],
        "signals": signals,
    }


class TestAnalyzeGap:

    def test_returns_string(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import analyze_gap
        result = analyze_gap("pilates body", sample_topic_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_uses_topic_name_in_prompt(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import analyze_gap
        analyze_gap("pilates body", sample_topic_data)
        call_args = mock_claude["client"].messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "pilates body" in prompt

    def test_no_user_thesis_does_not_crash(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import analyze_gap
        result = analyze_gap("pilates body", sample_topic_data, user_thesis=None)
        assert isinstance(result, str)

    def test_with_user_thesis_includes_context(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import analyze_gap
        thesis = {
            "build_profile": "Solo developer focused on health apps",
            "domains": ["fitness", "wellness"],
            "skills": ["React Native", "Python"],
            "avoid_domains": ["crypto"],
        }
        analyze_gap("pilates body", sample_topic_data, user_thesis=thesis)
        call_args = mock_claude["client"].messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Solo developer" in prompt or "fitness" in prompt


class TestGenerateOpportunityBrief:

    def test_returns_string(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import generate_opportunity_brief
        result = generate_opportunity_brief(
            "pilates body", sample_topic_data,
            gap_analysis="Gap analysis text",
        )
        assert isinstance(result, str)

    def test_institutional_knowledge_injected_in_prompt(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import generate_opportunity_brief
        generate_opportunity_brief(
            "pilates body", sample_topic_data,
            gap_analysis="Gap text",
            institutional_knowledge="Past insight: health apps do well in Jan",
        )
        call_args = mock_claude["client"].messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Past insight" in prompt

    def test_no_institutional_knowledge_no_crash(self, mock_claude, sample_topic_data):
        from pipeline.synthesis.claude import generate_opportunity_brief
        result = generate_opportunity_brief(
            "pilates body", sample_topic_data,
            gap_analysis="Gap text",
            institutional_knowledge=None,
        )
        assert isinstance(result, str)


class TestAssessAppFit:

    def _make_valid_json_response(self, mock_claude):
        """Set mock to return valid JSON."""
        valid = {
            "mobile_native": 0.8,
            "daily_use": 0.7,
            "simple_enough": 0.9,
            "monetizable": 0.6,
            "market_size": 0.7,
            "competition_thin": 0.8,
            "overall_fit": 0.75,
            "app_concept": "Daily pilates tracker with progress photos",
            "build_recommendation": "YES",
            "reasoning": "Strong mobile fit, thin App Store supply."
        }
        mock_claude["response"].content[0].text = json.dumps(valid)
        return valid

    def test_valid_json_parsed_correctly(self, mock_claude):
        from pipeline.synthesis.claude import assess_app_fit
        self._make_valid_json_response(mock_claude)
        result = assess_app_fit("pilates body", "Brief text", "Gap text")
        assert result["overall_fit"] == pytest.approx(0.75, abs=0.01)
        assert result["build_recommendation"] == "YES"

    def test_invalid_json_returns_fallback(self, mock_claude):
        """Claude returning non-JSON should not crash — returns fallback dict."""
        from pipeline.synthesis.claude import assess_app_fit
        mock_claude["response"].content[0].text = "Sorry, I cannot assess this."
        result = assess_app_fit("pilates body", "Brief text", "Gap text")
        assert isinstance(result, dict)
        assert "overall_fit" in result
        assert result["overall_fit"] == pytest.approx(0.0, abs=0.01)
        assert result["build_recommendation"] == "NO"

    def test_partial_json_in_surrounding_text(self, mock_claude):
        """JSON embedded in prose text should still be parsed."""
        from pipeline.synthesis.claude import assess_app_fit
        mock_claude["response"].content[0].text = (
            'Here is my assessment:\n'
            '{"mobile_native": 0.9, "daily_use": 0.8, "simple_enough": 0.7, '
            '"monetizable": 0.6, "market_size": 0.7, "competition_thin": 0.8, '
            '"overall_fit": 0.75, "app_concept": "Test app", '
            '"build_recommendation": "YES", "reasoning": "Good fit."}'
        )
        result = assess_app_fit("pilates body", "Brief text", "Gap text")
        assert result["overall_fit"] == pytest.approx(0.75, abs=0.01)

    def test_returns_dict_always(self, mock_claude):
        """Whatever Claude returns, assess_app_fit must return a dict."""
        from pipeline.synthesis.claude import assess_app_fit
        for response_text in ["", "null", "{}", "true", "123"]:
            mock_claude["response"].content[0].text = response_text
            result = assess_app_fit("test", "brief", "gap")
            assert isinstance(result, dict)
