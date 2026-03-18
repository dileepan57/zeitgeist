from fastapi import APIRouter, Query
from pipeline.utils import db

router = APIRouter()


@router.get("")
def get_opportunities(
    date: str | None = None,
    timeline: str | None = None,
    min_score: float = 0.0,
    limit: int = 20,
):
    """Get ranked opportunities, optionally filtered."""
    client = db.get_client()

    # Get latest run if no date specified
    if date:
        runs = client.table("daily_runs").select("id").eq("run_date", date).execute().data
    else:
        runs = client.table("daily_runs").select("id,run_date").eq("status", "complete").order("run_date", desc=True).limit(1).execute().data

    if not runs:
        return {"opportunities": [], "run_date": date}

    run_id = runs[0]["id"]
    run_date = runs[0].get("run_date", date)

    # Get scores for this run
    query = client.table("topic_scores").select(
        "*, topics(name, canonical_name, first_seen)"
    ).eq("run_id", run_id).gte("opportunity_score", min_score).order("opportunity_score", desc=True).limit(limit)

    if timeline:
        query = query.eq("timeline_position", timeline)

    scores = query.execute().data

    # Fetch syntheses separately and merge by topic_id (no direct FK to join on)
    if scores:
        topic_ids = [s["topic_id"] for s in scores]
        syntheses = client.table("topic_syntheses").select(
            "topic_id, gap_analysis, opportunity_brief, app_fit_score, app_concept"
        ).eq("run_id", run_id).in_("topic_id", topic_ids).execute().data
        syntheses_map = {s["topic_id"]: s for s in syntheses}
        for score in scores:
            score["topic_syntheses"] = syntheses_map.get(score["topic_id"])

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
