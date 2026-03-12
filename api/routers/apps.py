from fastapi import APIRouter
from pydantic import BaseModel
from pipeline.utils import db

router = APIRouter()


class AppProjectPayload(BaseModel):
    name: str
    opportunity_topic_id: str | None = None
    bundle_id: str | None = None


class TaskApproval(BaseModel):
    approved: bool
    user_note: str | None = None


@router.get("")
def list_apps():
    client = db.get_client()
    apps = client.table("app_projects").select("*, app_builds(*), app_revenue(*)").order("created_at", desc=True).execute().data
    return {"apps": apps}


@router.get("/{app_id}")
def get_app(app_id: str):
    client = db.get_client()
    app = client.table("app_projects").select("*").eq("id", app_id).execute().data
    builds = client.table("app_builds").select("*").eq("project_id", app_id).order("created_at", desc=True).execute().data
    revenue = client.table("app_revenue").select("*").eq("project_id", app_id).order("date", desc=True).limit(30).execute().data
    tasks = client.table("app_tasks").select("*").eq("project_id", app_id).order("created_at", desc=True).limit(20).execute().data
    return {"app": app[0] if app else None, "builds": builds, "revenue": revenue, "tasks": tasks}


@router.post("")
def create_app(payload: AppProjectPayload):
    record = db.insert("app_projects", payload.model_dump(exclude_none=True))
    return record[0]


@router.post("/{app_id}/tasks/{task_id}/approve")
def approve_task(app_id: str, task_id: str, payload: TaskApproval):
    db.update("app_tasks", {"id": task_id}, {
        "user_approved": payload.approved,
        "status": "APPROVED" if payload.approved else "PENDING",
    })
    return {"status": "updated"}


@router.post("/{app_id}/build")
def trigger_build(app_id: str):
    """Trigger EAS build for an app project."""
    import subprocess
    import threading
    from datetime import date

    app = db.select("app_projects", filters={"id": app_id})
    if not app:
        return {"error": "App not found"}

    build_record = db.insert("app_builds", {
        "project_id": app_id,
        "build_date": date.today().isoformat(),
        "platform": "all",
        "status": "building",
    })
    build_id = build_record[0]["id"]

    def run_eas_build():
        try:
            result = subprocess.run(
                ["eas", "build", "--platform", "all", "--non-interactive"],
                capture_output=True, text=True,
                cwd=f"apps/{app[0]['name']}",
            )
            status = "finished" if result.returncode == 0 else "errored"
        except Exception:
            status = "errored"
        db.update("app_builds", {"id": build_id}, {"status": status})

    threading.Thread(target=run_eas_build, daemon=True).start()
    return {"status": "build_triggered", "build_id": build_id}
