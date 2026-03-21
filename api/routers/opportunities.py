import httpx
from fastapi import APIRouter, Query
from pipeline.utils import db

router = APIRouter()

WIKIPEDIA_BATCH_API = "https://en.wikipedia.org/w/api.php"


def _fetch_descriptions(topic_names: list[str]) -> dict[str, str]:
    """
    Batch-fetch first-sentence Wikipedia descriptions.
    Returns dict of lowercase topic name → description string.
    """
    if not topic_names:
        return {}
    result = {}
    try:
        for i in range(0, len(topic_names), 50):
            batch = topic_names[i:i + 50]
            resp = httpx.get(
                WIKIPEDIA_BATCH_API,
                params={
                    "action": "query",
                    "titles": "|".join(batch),
                    "prop": "extracts",
                    "exsentences": 1,
                    "exintro": 1,
                    "explaintext": 1,
                    "redirects": 1,
                    "format": "json",
                },
                headers={"User-Agent": "zeitgeist/1.0"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for page in data.get("query", {}).get("pages", {}).values():
                title = page.get("title", "")
                extract = (page.get("extract") or "").strip()
                if extract and not extract.startswith("=="):
                    sentence = extract.split(".")[0].strip()
                    if len(sentence) > 10:
                        result[title.lower()] = sentence + "."
    except Exception:
        pass
    return result


@router.get("")
def get_opportunities(
    date: str | None = None,
    timeline: str | None = None,
    min_score: float = 0.0,
    limit: int = 40,
):
    """Get ranked attention topics with per-source signal counts and descriptions."""
    client = db.get_client()

    if date:
        runs = client.table("daily_runs").select("id").eq("run_date", date).execute().data
    else:
        runs = (
            client.table("daily_runs")
            .select("id,run_date")
            .eq("status", "complete")
            .order("run_date", desc=True)
            .limit(1)
            .execute().data
        )

    if not runs:
        return {"opportunities": [], "run_date": date}

    run_id = runs[0]["id"]
    run_date = runs[0].get("run_date", date)

    query = (
        client.table("topic_scores")
        .select("*, topics(name, canonical_name, first_seen)")
        .eq("run_id", run_id)
        .gte("opportunity_score", min_score)
        .order("independence_score", desc=True)
        .order("opportunity_score", desc=True)
        .limit(limit)
    )
    if timeline:
        query = query.eq("timeline_position", timeline)

    scores = query.execute().data

    if not scores:
        return {"opportunities": [], "run_date": run_date, "run_id": run_id, "count": 0}

    topic_ids = [s["topic_id"] for s in scores]

    # Per-source raw values from topic_signals
    signals_data = (
        client.table("topic_signals")
        .select("topic_id, signal_source, raw_value, fired")
        .eq("run_id", run_id)
        .in_("topic_id", topic_ids)
        .execute().data
    )
    signals_by_topic: dict[str, dict] = {}
    for sig in signals_data:
        tid = sig["topic_id"]
        if sig.get("fired") and sig.get("raw_value") is not None:
            signals_by_topic.setdefault(tid, {})[sig["signal_source"]] = sig["raw_value"]

    # Resolve topic names
    def _topic_name(score: dict) -> str:
        t = score.get("topics") or {}
        if isinstance(t, dict):
            return t.get("name") or ""
        if isinstance(t, list) and t:
            return t[0].get("name") or ""
        return ""

    topic_names = [_topic_name(s) for s in scores]

    # Batch Wikipedia descriptions (one HTTP request)
    descriptions = _fetch_descriptions([n for n in topic_names if n])

    # Enrich each score record
    for score, name in zip(scores, topic_names):
        score["signals_by_source"] = signals_by_topic.get(score["topic_id"], {})
        score["description"] = descriptions.get(name.lower(), "")

    return {
        "run_date": run_date,
        "run_id": run_id,
        "count": len(scores),
        "opportunities": scores,
    }


@router.post("/trigger")
def trigger_pipeline():
    """Trigger an on-demand pipeline run."""
    import subprocess
    import threading

    def run_pipeline():
        subprocess.run(["python", "-m", "pipeline.run"], check=True)

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return {"status": "triggered", "message": "Pipeline started in background"}
