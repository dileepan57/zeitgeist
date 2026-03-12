from fastapi import APIRouter
from pipeline.utils import db

router = APIRouter()


@router.get("")
def list_runs(limit: int = 30):
    client = db.get_client()
    runs = client.table("daily_runs").select("*").order("run_date", desc=True).limit(limit).execute().data
    return {"runs": runs}


@router.get("/{run_date}")
def get_run(run_date: str):
    client = db.get_client()
    runs = client.table("daily_runs").select("*").eq("run_date", run_date).execute().data
    if not runs:
        return {"error": "Run not found"}
    return runs[0]
