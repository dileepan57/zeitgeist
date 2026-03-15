"""
Eval 3: Gap Analysis Quality
For each topic in known_real_markets.json, run analyze_gap() and score output
against a rubric: specificity (1-5), evidence-grounding (1-5), actionability (1-5).
Scoring done by a second Claude call. Threshold: avg score >= 3.5.

Costs ~$0.05 per run (15 topics × 2 Claude calls each).
"""
import json
import os
from pathlib import Path
from loguru import logger

RUBRIC_THRESHOLD = 3.5
DATASET_PATH = Path(__file__).parent / "datasets" / "known_real_markets.json"
EVAL_SAMPLE_SIZE = 5  # Evaluate a subset to control cost


def run_gap_analysis_eval() -> dict:
    """
    Run gap analysis on sample of known real markets and score quality via Claude.
    Returns gap analysis eval result.
    """
    try:
        from pipeline.synthesis.claude import analyze_gap, get_client, MODEL

        with open(DATASET_PATH) as f:
            markets = json.load(f)

        # Sample to control cost
        sample = markets[:EVAL_SAMPLE_SIZE]
        scores = []
        failures = []

        for market in sample:
            topic = market["topic"]
            logger.info(f"Gap analysis eval: {topic}")
            try:
                # Build minimal scored_topic from known market data
                scored_topic = _build_scored_topic(market)
                gap_text = analyze_gap(topic, scored_topic)
                rubric_scores = _score_with_rubric(topic, gap_text, market, get_client(), MODEL)
                scores.append(rubric_scores)
            except Exception as e:
                logger.warning(f"Gap analysis eval failed for {topic}: {e}")
                failures.append({"topic": topic, "error": str(e)})

        if not scores:
            return {
                "eval_name": "gap_analysis",
                "metric_name": "rubric_avg_score",
                "metric_value": None,
                "threshold": RUBRIC_THRESHOLD,
                "passed": False,
                "details": {"error": "All evaluations failed", "failures": failures},
            }

        # Average across all dimensions and topics
        avg_specificity = sum(s["specificity"] for s in scores) / len(scores)
        avg_evidence = sum(s["evidence_grounding"] for s in scores) / len(scores)
        avg_actionability = sum(s["actionability"] for s in scores) / len(scores)
        overall_avg = (avg_specificity + avg_evidence + avg_actionability) / 3
        passed = overall_avg >= RUBRIC_THRESHOLD

        logger.info(f"Gap analysis eval: avg={overall_avg:.2f}, passed={passed}")

        return {
            "eval_name": "gap_analysis",
            "metric_name": "rubric_avg_score",
            "metric_value": round(overall_avg, 4),
            "threshold": RUBRIC_THRESHOLD,
            "passed": passed,
            "details": {
                "sample_size": len(scores),
                "avg_specificity": round(avg_specificity, 3),
                "avg_evidence_grounding": round(avg_evidence, 3),
                "avg_actionability": round(avg_actionability, 3),
                "overall_avg": round(overall_avg, 3),
                "per_topic_scores": scores,
                "failures": failures,
            },
        }

    except Exception as e:
        logger.warning(f"Gap analysis eval error: {e}")
        return {
            "eval_name": "gap_analysis",
            "metric_name": "rubric_avg_score",
            "metric_value": None,
            "threshold": RUBRIC_THRESHOLD,
            "passed": False,
            "details": {"error": str(e)},
        }


def _build_scored_topic(market: dict) -> dict:
    """Build a synthetic scored_topic dict from known market data for eval input."""
    lead_signals = market.get("lead_signals", [])
    return {
        "topic": market["topic"],
        "independence_score": min(len(lead_signals) / 6, 1.0),
        "demand_score": 0.7 if "google_trends" in lead_signals or "wikipedia" in lead_signals else 0.4,
        "frustration_score": 0.6,
        "supply_gap_score": 0.7,
        "timeline_position": market.get("timeline_position_at_opportunity", "CRYSTALLIZING"),
        "opportunity_score": 0.75,
        "adjusted_categories": lead_signals[:4],
        "sources_fired": lead_signals,
        "vocabulary_fragmentation": 0.5,
        "variant_count": 8,
        "lead_indicator_ratio": 0.6,
        "vocab_interpretation": "Moderate fragmentation — category not yet branded",
    }


def _score_with_rubric(topic: str, gap_text: str, market: dict, client, model: str) -> dict:
    """Score gap analysis output against rubric via a second Claude call."""
    gap_desc = market.get("gap_description", "")
    prompt = f"""You are evaluating the quality of a market gap analysis. Score it on three dimensions.

Topic: "{topic}"
Known gap: "{gap_desc}"

Gap analysis to score:
---
{gap_text}
---

Score each dimension from 1 (poor) to 5 (excellent):

1. SPECIFICITY (1-5): Does it name specific pain points, quotes, or examples? Or vague generalities?
   - 5: Multiple specific examples, named pain points, concrete quotes or data points
   - 3: Some specificity but mixed with generalities
   - 1: Entirely generic, could apply to any topic

2. EVIDENCE_GROUNDING (1-5): Are claims supported by signal data? Or invented?
   - 5: References actual signal sources (Reddit, App Store reviews, search trends) explicitly
   - 3: Implies evidence exists but doesn't ground it specifically
   - 1: Asserts gaps without any signal grounding

3. ACTIONABILITY (1-5): Would a builder know what to do next?
   - 5: Clear who to build for, what pain to solve, what MVP would look like
   - 3: Directionally useful but requires more research
   - 1: Would need to start from scratch to build anything

Respond in this exact JSON format:
{{
  "topic": "{topic}",
  "specificity": 0,
  "evidence_grounding": 0,
  "actionability": 0,
  "reasoning": "..."
}}"""

    response = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {"topic": topic, "specificity": 2, "evidence_grounding": 2, "actionability": 2, "reasoning": text}
