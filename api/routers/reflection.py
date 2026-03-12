from fastapi import APIRouter
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
