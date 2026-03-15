from fastapi import APIRouter, Query
from pydantic import BaseModel
from pipeline.utils import db

router = APIRouter()


class OutcomePayload(BaseModel):
    recommendation_id: str
    outcome_type: str  # REAL_MARKET | FIZZLED | EMERGING | MISSED
    evidence: str | None = None
    user_note: str | None = None


@router.get("")
def get_reflection():
    client = db.get_client()

    signal_perf = client.table("signal_performance").select("*").order("precision", desc=True).execute().data
    knowledge = client.table("institutional_knowledge").select("*").order("version", desc=True).limit(1).execute().data
    outcomes = client.table("outcomes").select("*, recommendations(topic_id, topics(name))").limit(50).execute().data

    by_type: dict[str, int] = {}
    for o in outcomes:
        t = o.get("outcome_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "signal_performance": signal_perf,
        "current_knowledge": knowledge[0] if knowledge else None,
        "outcome_summary": by_type,
        "recent_outcomes": outcomes[:20],
    }


@router.post("/outcomes")
def record_outcome(payload: OutcomePayload):
    from datetime import date
    db.insert("outcomes", {
        "recommendation_id": payload.recommendation_id,
        "outcome_date": date.today().isoformat(),
        "outcome_type": payload.outcome_type,
        "evidence": payload.evidence,
        "user_note": payload.user_note,
        "auto_detected": False,
    })
    return {"status": "recorded"}


@router.get("/history")
def get_signal_performance_history(
    source: str | None = Query(None, description="Filter by signal source"),
    limit: int = Query(90, description="Max rows to return"),
):
    """Return historical signal performance snapshots over time (weekly calibration snapshots)."""
    client = db.get_client()
    query = (
        client.table("signal_perf_history")
        .select("*")
        .order("snapshot_date", desc=True)
        .limit(limit)
    )
    if source:
        query = query.eq("signal_source", source)
    rows = query.execute().data or []

    # Group by source for trend lines
    by_source: dict[str, list] = {}
    for row in rows:
        s = row.get("signal_source", "unknown")
        if s not in by_source:
            by_source[s] = []
        by_source[s].append({
            "date": row.get("snapshot_date"),
            "precision": row.get("precision"),
            "recall": row.get("recall"),
            "true_positives": row.get("true_positives"),
            "false_positives": row.get("false_positives"),
        })

    # Sort each source's history chronologically
    for s in by_source:
        by_source[s].sort(key=lambda r: r["date"] or "")

    return {
        "by_source": by_source,
        "total_snapshots": len(rows),
        "sources": list(by_source.keys()),
    }


@router.get("/misses")
def get_misses(limit: int = Query(20, description="Max misses to return")):
    """
    Return topics the system missed — real market opportunities that were never recommended.
    Auto-detected by checking outcomes with type=MISSED and topics with no high-score recommendation.
    """
    client = db.get_client()

    # Explicit MISSED outcomes
    missed_outcomes = (
        client.table("outcomes")
        .select("*, recommendations(topic_id, confidence_score, topics(name))")
        .eq("outcome_type", "MISSED")
        .order("outcome_date", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    # Topics that emerged as REAL_MARKET but had low confidence scores when recommended
    low_conf_real = (
        client.table("outcomes")
        .select("recommendation_id, recommendations(topic_id, confidence_score, topics(name)), outcome_date")
        .eq("outcome_type", "REAL_MARKET")
        .execute()
        .data or []
    )
    underconfident = [
        o for o in low_conf_real
        if o.get("recommendations", {}) and (o["recommendations"].get("confidence_score") or 1.0) < 0.4
    ]

    return {
        "explicit_misses": missed_outcomes,
        "underconfident_real_markets": underconfident[:limit],
        "total_explicit_misses": len(missed_outcomes),
        "total_underconfident": len(underconfident),
        "miss_analysis": {
            "note": "Explicit misses are manually tagged. Underconfident = REAL_MARKET outcome but confidence_score < 0.4 when recommended.",
        },
    }


@router.get("/knowledge/history")
def get_knowledge_history(limit: int = Query(20, description="Max versions to return")):
    """Return all institutional knowledge versions in reverse chronological order."""
    client = db.get_client()
    versions = (
        client.table("institutional_knowledge")
        .select("id, version, performance_summary, created_at, knowledge_brief")
        .order("version", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )
    return {
        "versions": versions,
        "total": len(versions),
        "latest_version": versions[0]["version"] if versions else None,
    }
