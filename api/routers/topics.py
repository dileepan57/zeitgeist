from fastapi import APIRouter
from pipeline.utils import db

router = APIRouter()


@router.get("/{topic_id}")
def get_topic(topic_id: str):
    client = db.get_client()

    topic = client.table("topics").select("*").eq("id", topic_id).execute().data
    if not topic:
        return {"error": "Topic not found"}

    scores = client.table("topic_scores").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(10).execute().data
    signals = client.table("topic_signals").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(50).execute().data
    syntheses = client.table("topic_syntheses").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(5).execute().data
    outcomes = client.table("outcomes").select("*, recommendations(topic_id)").execute().data

    topic_outcomes = [o for o in outcomes if o.get("recommendations", {}).get("topic_id") == topic_id]

    return {
        "topic": topic[0],
        "scores": scores,
        "signals": signals,
        "syntheses": syntheses,
        "outcomes": topic_outcomes,
    }
