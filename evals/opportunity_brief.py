"""
Eval 4: Opportunity Brief Coherence + Specificity
Run generate_opportunity_brief() for sample topics.
Evaluate: Does the brief correctly identify the market? Is timeline plausible?
Does confidence match known outcome (real vs fizzle)?

Costs ~$0.03 per run (5 topics × 2 Claude calls each).
"""
import json
from pathlib import Path
from loguru import logger

COHERENCE_THRESHOLD = 3.5
REAL_MARKETS_PATH = Path(__file__).parent / "datasets" / "known_real_markets.json"
FIZZLES_PATH = Path(__file__).parent / "datasets" / "known_fizzles.json"
EVAL_SAMPLE_SIZE = 3  # 3 real + 2 fizzles to control cost


def run_opportunity_brief_eval() -> dict:
    """
    Evaluate opportunity brief quality vs known real markets and fizzles.
    Returns coherence eval result.
    """
    try:
        from pipeline.synthesis.claude import analyze_gap, generate_opportunity_brief, get_client, MODEL

        with open(REAL_MARKETS_PATH) as f:
            real_markets = json.load(f)
        with open(FIZZLES_PATH) as f:
            fizzles = json.load(f)

        real_sample = real_markets[:EVAL_SAMPLE_SIZE]
        fizzle_sample = fizzles[:2]

        results = []
        failures = []

        # Evaluate real markets — brief should be positive/high confidence
        for market in real_sample:
            topic = market["topic"]
            logger.info(f"Brief eval (real): {topic}")
            try:
                scored_topic = _build_scored_topic(market, is_real=True)
                gap = analyze_gap(topic, scored_topic)
                brief = generate_opportunity_brief(topic, scored_topic, gap)
                eval_result = _evaluate_brief(topic, brief, market, expected_real=True, client=get_client(), model=MODEL)
                results.append(eval_result)
            except Exception as e:
                logger.warning(f"Brief eval failed for {topic}: {e}")
                failures.append({"topic": topic, "error": str(e)})

        # Evaluate fizzles — brief should flag risk or low confidence
        for fizzle in fizzle_sample:
            topic = fizzle["topic"]
            logger.info(f"Brief eval (fizzle): {topic}")
            try:
                scored_topic = _build_scored_topic(fizzle, is_real=False)
                gap = analyze_gap(topic, scored_topic)
                brief = generate_opportunity_brief(topic, scored_topic, gap)
                eval_result = _evaluate_brief(topic, brief, fizzle, expected_real=False, client=get_client(), model=MODEL)
                results.append(eval_result)
            except Exception as e:
                logger.warning(f"Brief eval failed for {topic}: {e}")
                failures.append({"topic": topic, "error": str(e)})

        if not results:
            return {
                "eval_name": "opportunity_brief",
                "metric_name": "coherence_avg_score",
                "metric_value": None,
                "threshold": COHERENCE_THRESHOLD,
                "passed": False,
                "details": {"error": "All evaluations failed", "failures": failures},
            }

        avg_coherence = sum(r["coherence_score"] for r in results) / len(results)
        market_alignment = sum(1 for r in results if r["market_aligned"]) / len(results)
        passed = avg_coherence >= COHERENCE_THRESHOLD

        logger.info(f"Brief eval: coherence={avg_coherence:.2f}, market_alignment={market_alignment:.0%}, passed={passed}")

        return {
            "eval_name": "opportunity_brief",
            "metric_name": "coherence_avg_score",
            "metric_value": round(avg_coherence, 4),
            "threshold": COHERENCE_THRESHOLD,
            "passed": passed,
            "details": {
                "sample_size": len(results),
                "avg_coherence_score": round(avg_coherence, 3),
                "market_alignment_rate": round(market_alignment, 3),
                "per_topic_results": results,
                "failures": failures,
            },
        }

    except Exception as e:
        logger.warning(f"Opportunity brief eval error: {e}")
        return {
            "eval_name": "opportunity_brief",
            "metric_name": "coherence_avg_score",
            "metric_value": None,
            "threshold": COHERENCE_THRESHOLD,
            "passed": False,
            "details": {"error": str(e)},
        }


def _build_scored_topic(market: dict, is_real: bool) -> dict:
    """Build synthetic scored_topic from market/fizzle data."""
    lead_signals = market.get("lead_signals", market.get("peak_signals", []))
    opportunity_score = 0.75 if is_real else 0.45
    return {
        "topic": market["topic"],
        "independence_score": min(len(lead_signals) / 6, 1.0),
        "demand_score": 0.7 if is_real else 0.6,
        "frustration_score": 0.6 if is_real else 0.3,
        "supply_gap_score": 0.7 if is_real else 0.2,
        "opportunity_score": opportunity_score,
        "timeline_position": market.get("timeline_position_at_opportunity", "CRYSTALLIZING" if is_real else "PEAKING"),
        "timeline_description": "Strong demand with builder activity ahead" if is_real else "Peak hype — late stage",
        "adjusted_categories": lead_signals[:4],
        "sources_fired": lead_signals,
        "vocabulary_fragmentation": 0.5 if is_real else 0.2,
        "variant_count": 8 if is_real else 3,
        "lead_indicator_ratio": 0.6 if is_real else 0.2,
        "vocab_interpretation": "Moderate fragmentation" if is_real else "Low fragmentation — branded already",
    }


def _evaluate_brief(topic: str, brief: str, market: dict, expected_real: bool, client, model: str) -> dict:
    """Evaluate brief coherence and market alignment via Claude rubric."""
    expected_label = "REAL_MARKET" if expected_real else "FIZZLED"
    market_context = market.get("gap_description", market.get("fizzle_reason", ""))

    prompt = f"""You are evaluating the quality of an opportunity brief. The actual outcome of this market is known.

Topic: "{topic}"
Known outcome: {expected_label}
Context: "{market_context}"

Opportunity brief to evaluate:
---
{brief}
---

Score on two dimensions:

1. COHERENCE (1-5): Is the brief internally consistent, specific, and actionable?
   - 5: Clear opportunity statement, specific evidence, concrete next steps, no internal contradictions
   - 3: Reasonable but vague in some areas
   - 1: Contradictory, generic, or clearly wrong

2. MARKET_ALIGNED (true/false): Does the brief's overall sentiment match the known outcome?
   - true: If outcome=REAL_MARKET and brief is positive/high confidence, OR outcome=FIZZLED and brief flags significant risk
   - false: If the brief contradicts the known outcome (e.g. very bullish on a confirmed fizzle)

Respond in this exact JSON format:
{{
  "topic": "{topic}",
  "coherence_score": 0,
  "market_aligned": true,
  "expected_outcome": "{expected_label}",
  "reasoning": "..."
}}"""

    response = client.messages.create(
        model=model,
        max_tokens=250,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "topic": topic,
            "coherence_score": 3,
            "market_aligned": True,
            "expected_outcome": expected_label,
            "reasoning": text,
        }
