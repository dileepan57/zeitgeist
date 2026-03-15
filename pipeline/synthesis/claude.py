"""
Claude API synthesis layer.
Two calls per top topic:
1. Gap analysis (frustration + supply gap + vocabulary)
2. Opportunity brief (narrative + institutional knowledge injected)
"""
import os
import time
import anthropic
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# run_id context — set by pipeline/run.py before synthesis begins
_current_run_id: str | None = None


def set_run_id(run_id: str | None):
    global _current_run_id
    _current_run_id = run_id


def _tracked_call(call_type: str, topic: str | None, fn, *args, **kwargs):
    """Wrap a Claude API call with timing and usage tracking."""
    start = time.time()
    try:
        response = fn(*args, **kwargs)
        duration_ms = int((time.time() - start) * 1000)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
        try:
            from pipeline.telemetry.store import flush_claude_usage
            flush_claude_usage(
                run_id=_current_run_id,
                call_type=call_type,
                topic=topic,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=True,
            )
        except Exception:
            pass
        return response
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        try:
            from pipeline.telemetry.store import flush_claude_usage
            flush_claude_usage(
                run_id=_current_run_id,
                call_type=call_type,
                topic=topic,
                input_tokens=0,
                output_tokens=0,
                duration_ms=duration_ms,
                success=False,
                error_msg=str(e),
            )
        except Exception:
            pass
        raise

MODEL = "claude-sonnet-4-6"
_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def analyze_gap(topic: str, scored_topic: dict, user_thesis: dict | None = None) -> str:
    """
    Call 1: Gap analysis.
    Analyzes what people are asking that has no good answer,
    existing solution flaws, and underserved segments.
    """
    signals_summary = _format_signals(scored_topic)
    thesis_context = _format_thesis(user_thesis)

    prompt = f"""You are an opportunity analyst identifying genuine gaps in the market.

Topic: "{topic}"

Signal data:
{signals_summary}

{thesis_context}

Analyze this topic for market gaps. Be specific and evidence-based. Answer:

1. WHAT PEOPLE ARE ASKING: What specific questions/needs are people expressing about this topic that don't have good answers? (Look for frustration signals, Reddit complaints, search queries)

2. EXISTING SOLUTION FLAWS: What do current solutions get wrong? What complaints are common? (If supply gap score is high, note that few good solutions exist)

3. UNDERSERVED SEGMENTS: Who is being left out by existing solutions? (demographics, use cases, price points)

4. VOCABULARY SIGNAL: {scored_topic.get('vocab_interpretation', 'N/A')} — What does this mean about category maturity?

5. SUPPLY GAP EVIDENCE: Gap score is {scored_topic.get('supply_gap_score', 0):.2f}/1.0. What specific evidence supports or contradicts this?

Be direct. 3-4 sentences per section. No fluff."""

    response = _tracked_call(
        "gap_analysis", topic,
        get_client().messages.create,
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_opportunity_brief(
    topic: str,
    scored_topic: dict,
    gap_analysis: str,
    institutional_knowledge: str | None = None,
    user_thesis: dict | None = None,
) -> str:
    """
    Call 2: Full opportunity brief.
    Synthesizes gap analysis into actionable opportunity brief.
    Injects institutional knowledge from self-reflection module.
    """
    signals_summary = _format_signals(scored_topic)
    thesis_context = _format_thesis(user_thesis)
    knowledge_context = f"\n\nINSTITUTIONAL KNOWLEDGE (from past predictions):\n{institutional_knowledge}" if institutional_knowledge else ""

    prompt = f"""You are a product opportunity analyst with a strong track record of spotting opportunities early.

Topic: "{topic}"
Timeline position: {scored_topic.get('timeline_position', 'UNKNOWN')} — {scored_topic.get('timeline_description', '')}
Opportunity score: {scored_topic.get('opportunity_score', 0):.2f}/1.0
Categories firing: {', '.join(scored_topic.get('adjusted_categories', []))}
Lead indicator ratio: {scored_topic.get('lead_indicator_ratio', 0):.0%} (builder signals vs. total)

Gap analysis:
{gap_analysis}

Signal summary:
{signals_summary}
{knowledge_context}
{thesis_context}

Write a concise opportunity brief with these sections:

**WHY NOW**: Why is this the right moment? What has changed to make this addressable?

**THE OPPORTUNITY**: In one sentence: what product/service would win here and for whom?

**EVIDENCE OF DEMAND**: Strongest 2-3 signals confirming real unmet need.

**RISK**: What could make this fizzle? What would you need to see to confirm it's real?

**WHAT TO WATCH**: 2-3 leading indicators to monitor over the next 30-90 days.

**HISTORICAL PATTERN**: Does this resemble any known opportunity pattern? (e.g., "similar to early Notion, where people used spreadsheets for something they needed a dedicated tool for")

Be specific and actionable. Write for a builder who needs to decide in the next 30 seconds whether to dig deeper."""

    response = _tracked_call(
        "opportunity_brief", topic,
        get_client().messages.create,
        model=MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def assess_app_fit(topic: str, opportunity_brief: str, gap_analysis: str) -> dict:
    """
    Assess whether this opportunity is addressable as a mobile app.
    Returns {app_fit_score, app_concept, reasoning}
    """
    prompt = f"""Topic: "{topic}"

Opportunity brief:
{opportunity_brief}

Gap analysis:
{gap_analysis}

Assess whether this opportunity is well-suited to a mobile app. Score each dimension 0-1:

1. mobile_native (0-1): Does it benefit from mobile-specific features? (camera, GPS, push notifications, on-the-go access)
2. daily_use (0-1): Would users open this app daily vs. rarely?
3. simple_enough (0-1): Can a meaningful MVP be built in 1-2 weeks by 1 developer?
4. monetizable (0-1): Would users pay $1/month for this?
5. market_size (0-1): Is the potential audience large enough to matter?
6. competition_thin (0-1): Is the App Store space thin or poorly served for this need?

Then provide:
- app_concept: One sentence describing the specific app (what it does, for whom)
- overall_fit: 0-1 composite score
- build_recommendation: YES | MAYBE | NO

Respond in this exact JSON format:
{{
  "mobile_native": 0.0,
  "daily_use": 0.0,
  "simple_enough": 0.0,
  "monetizable": 0.0,
  "market_size": 0.0,
  "competition_thin": 0.0,
  "overall_fit": 0.0,
  "app_concept": "...",
  "build_recommendation": "YES|MAYBE|NO",
  "reasoning": "..."
}}"""

    response = _tracked_call(
        "app_fit", topic,
        get_client().messages.create,
        model=MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    text = response.content[0].text
    try:
        # Extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"App fit JSON parse failed: {e}")
        return {"overall_fit": 0.0, "app_concept": "", "build_recommendation": "NO", "reasoning": text}


def _format_signals(scored_topic: dict) -> str:
    lines = [
        f"- Independence score: {scored_topic.get('independence_score', 0):.2f}/1.0 ({len(scored_topic.get('adjusted_categories', []))} independent categories)",
        f"- Actionability: demand={scored_topic.get('demand_score', 0):.2f}, frustration={scored_topic.get('frustration_score', 0):.2f}, supply_gap={scored_topic.get('supply_gap_score', 0):.2f}",
        f"- Sources firing: {', '.join(scored_topic.get('sources_fired', []))}",
        f"- Vocabulary fragmentation: {scored_topic.get('vocabulary_fragmentation', 0):.2f} ({scored_topic.get('variant_count', 0)} variants)",
    ]
    return "\n".join(lines)


def _format_thesis(user_thesis: dict | None) -> str:
    if not user_thesis:
        return ""
    parts = []
    if user_thesis.get("build_profile"):
        parts.append(f"Builder profile: {user_thesis['build_profile']}")
    if user_thesis.get("domains"):
        parts.append(f"Domains of interest: {', '.join(user_thesis['domains'])}")
    if user_thesis.get("skills"):
        parts.append(f"Skills: {', '.join(user_thesis['skills'])}")
    if user_thesis.get("avoid_domains"):
        parts.append(f"Avoid: {', '.join(user_thesis['avoid_domains'])}")
    return "\nUSER CONTEXT:\n" + "\n".join(parts) if parts else ""
