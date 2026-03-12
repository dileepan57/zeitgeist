"""
Institutional knowledge generator.
Periodically reflects on all outcomes and produces a knowledge brief
that gets injected into every future Claude synthesis call.
"""
import os
import anthropic
from loguru import logger
from pipeline.utils import db

MODEL = "claude-sonnet-4-6"


def generate_knowledge_brief() -> str | None:
    """
    Retrieve all outcomes, signal performance, and recent hits/misses.
    Ask Claude to synthesize institutional knowledge.
    Store in DB and return the brief.
    """
    logger.info("Generating institutional knowledge brief...")

    # Fetch recent outcomes
    outcomes = db.select("outcomes", limit=200)
    signal_perf = db.select("signal_performance", limit=50)

    if len(outcomes) < 5:
        logger.info("Not enough outcomes yet to generate meaningful knowledge")
        return None

    # Summarize outcomes
    by_type: dict[str, int] = {}
    for o in outcomes:
        t = o.get("outcome_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

    # Signal performance summary
    perf_lines = []
    for sp in signal_perf:
        p = sp.get("precision")
        r = sp.get("recall")
        if p is not None and r is not None:
            perf_lines.append(f"  {sp['signal_source']}: precision={p:.2f}, recall={r:.2f}, lead_time={sp.get('avg_lead_time_days', '?')}d")

    outcomes_summary = "\n".join([f"  {k}: {v}" for k, v in by_type.items()])
    perf_summary = "\n".join(perf_lines) if perf_lines else "  No performance data yet"

    # Recent hits and misses
    hits = [o for o in outcomes if o.get("outcome_type") == "REAL_MARKET"][:10]
    misses = [o for o in outcomes if o.get("outcome_type") == "MISSED"][:10]

    hits_text = "\n".join([f"  - {h.get('evidence', 'No detail')}" for h in hits]) or "  None yet"
    misses_text = "\n".join([f"  - {m.get('evidence', 'No detail')}" for m in misses]) or "  None yet"

    prompt = f"""You are the self-reflection module for an opportunity intelligence system called Zeitgeist.
Your job is to analyze the system's track record and produce an institutional knowledge brief
that will be injected into every future analysis to improve prediction accuracy.

OUTCOME SUMMARY:
{outcomes_summary}

SIGNAL PERFORMANCE:
{perf_summary}

RECENT HITS (opportunities that became real):
{hits_text}

RECENT MISSES (real opportunities we failed to flag):
{misses_text}

Write a concise institutional knowledge brief covering:

1. MOST PREDICTIVE SIGNAL COMBINATIONS: Which signal patterns have most reliably led to real opportunities?

2. COMMON FALSE POSITIVE PATTERNS: What signal combinations consistently produce noise?

3. SYSTEMATIC BLIND SPOTS: What types of opportunities do we systematically miss and why?

4. TIMING CALIBRATION: What's the average lead time from our signal to mainstream validation?

5. META-INSIGHTS: Any other patterns, anomalies, or lessons from the track record?

Be specific and quantitative where possible. This brief will be used to calibrate future predictions.
Keep it under 500 words."""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    brief = response.content[0].text

    # Get current version number
    existing = db.select("institutional_knowledge", limit=1)
    version = (max(k.get("version", 0) for k in existing) + 1) if existing else 1

    # Store
    db.insert("institutional_knowledge", {
        "version": version,
        "knowledge_brief": brief,
        "performance_summary": perf_summary,
    })

    logger.info(f"Institutional knowledge v{version} generated and stored")
    return brief


def get_latest_knowledge() -> str | None:
    """Fetch the most recent institutional knowledge brief."""
    rows = db.select("institutional_knowledge", limit=10)
    if not rows:
        return None
    latest = max(rows, key=lambda x: x.get("version", 0))
    return latest.get("knowledge_brief")
