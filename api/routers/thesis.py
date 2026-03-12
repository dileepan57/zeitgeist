from fastapi import APIRouter
from pydantic import BaseModel
from pipeline.utils import db

router = APIRouter()


class ThesisPayload(BaseModel):
    build_profile: str | None = None
    domains: list[str] | None = None
    skills: list[str] | None = None
    past_projects: str | None = None
    avoid_domains: list[str] | None = None


@router.get("")
def get_thesis():
    rows = db.select("user_thesis", limit=1)
    return rows[0] if rows else {}


@router.put("")
def update_thesis(payload: ThesisPayload):
    existing = db.select("user_thesis", limit=1)
    data = payload.model_dump(exclude_none=True)
    if existing:
        db.update("user_thesis", {"id": existing[0]["id"]}, data)
        return {"status": "updated"}
    else:
        db.insert("user_thesis", data)
        return {"status": "created"}
