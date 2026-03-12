"""
Daily agent session router.
Powers the conversational build companion.
"""
import os
from datetime import date
from fastapi import APIRouter
from pydantic import BaseModel
import anthropic
from pipeline.utils import db
from pipeline.reflection.knowledge import get_latest_knowledge

router = APIRouter()
MODEL = "claude-sonnet-4-6"


@router.get("/today")
def get_today_session():
    """Generate today's agent session brief."""
    client = db.get_client()

    # Top app-fit opportunities from today
    runs = client.table("daily_runs").select("id,run_date").eq("status", "complete").order("run_date", desc=True).limit(1).execute().data
    run_id = runs[0]["id"] if runs else None

    top_opportunities = []
    if run_id:
        scores = client.table("topic_scores").select(
            "*, topics(name), topic_syntheses(opportunity_brief, app_fit_score, app_concept)"
        ).eq("run_id", run_id).order("opportunity_score", desc=True).limit(10).execute().data

        for s in scores:
            syntheses = s.get("topic_syntheses") or [{}]
            syn = syntheses[0] if isinstance(syntheses, list) and syntheses else (syntheses if isinstance(syntheses, dict) else {})
            app_fit = syn.get("app_fit_score", 0) or 0
            if app_fit > 0.5:
                top_opportunities.append({
                    "topic": s.get("topics", {}).get("name") if isinstance(s.get("topics"), dict) else s.get("topics", [{}])[0].get("name"),
                    "opportunity_score": s.get("opportunity_score"),
                    "timeline_position": s.get("timeline_position"),
                    "app_fit_score": app_fit,
                    "app_concept": syn.get("app_concept"),
                    "opportunity_brief": syn.get("opportunity_brief", "")[:300],
                })

    # Active builds
    active_builds = client.table("app_projects").select(
        "*, app_tasks(status, task_description)"
    ).in_("status", ["BUILDING", "SUBMITTED"]).execute().data

    # Revenue summary
    revenue = client.table("app_revenue").select(
        "*, app_projects(name)"
    ).order("date", desc=True).limit(10).execute().data

    return {
        "date": date.today().isoformat(),
        "top_app_opportunities": top_opportunities[:3],
        "active_builds": active_builds,
        "revenue_summary": revenue,
    }


class SessionMessage(BaseModel):
    message: str
    app_id: str | None = None
    context: dict | None = None


@router.post("/message")
def send_session_message(payload: SessionMessage):
    """
    Conversational session with the build agent.
    Generates scaffold code, architecture advice, store copy, etc.
    """
    client_db = db.get_client()
    institutional_knowledge = get_latest_knowledge() or ""
    user_thesis = _get_thesis()

    # Build context from active app if provided
    app_context = ""
    if payload.app_id:
        app_data = client_db.table("app_projects").select("*").eq("id", payload.app_id).execute().data
        if app_data:
            app = app_data[0]
            tasks = client_db.table("app_tasks").select("*").eq("project_id", payload.app_id).order("created_at", desc=True).limit(5).execute().data
            app_context = f"\nActive app: {app['name']} (status: {app['status']})\nRecent tasks: {[t['task_description'] for t in tasks]}"

    system_prompt = f"""You are the Zeitgeist build agent — an expert React Native/Expo developer and product strategist.

Your role: Work collaboratively with the user to build mobile apps targeting real market opportunities.
You generate scaffolds, write features, create App Store copy, and guide the build process.

ALWAYS:
- Generate complete, working React Native/Expo code when asked
- Follow Expo Router file-based routing conventions
- Use TypeScript
- Integrate Supabase for backend, RevenueCat for subscriptions
- Be specific and actionable, not vague

USER CONTEXT:
{_format_thesis(user_thesis)}

INSTITUTIONAL KNOWLEDGE:
{institutional_knowledge[:500] if institutional_knowledge else "Building knowledge base..."}
{app_context}"""

    anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": payload.message}],
    )

    reply = response.content[0].text

    # If reply contains code, store as a pending task
    if payload.app_id and "```" in reply:
        db.insert("app_tasks", {
            "project_id": payload.app_id,
            "task_description": payload.message[:200],
            "generated_code": reply,
            "status": "PENDING",
            "user_approved": False,
        })

    return {"reply": reply, "task_created": payload.app_id is not None and "```" in reply}


def _get_thesis() -> dict | None:
    rows = db.select("user_thesis", limit=1)
    return rows[0] if rows else None


def _format_thesis(thesis: dict | None) -> str:
    if not thesis:
        return "No user thesis set yet."
    parts = []
    if thesis.get("build_profile"):
        parts.append(f"Builder: {thesis['build_profile']}")
    if thesis.get("domains"):
        parts.append(f"Domains: {', '.join(thesis['domains'])}")
    if thesis.get("skills"):
        parts.append(f"Skills: {', '.join(thesis['skills'])}")
    return "\n".join(parts) or "No thesis configured."
