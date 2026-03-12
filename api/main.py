from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from api.routers import runs, topics, opportunities, reflection, thesis, apps, session

app = FastAPI(title="Zeitgeist API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://zeitgeist.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
app.include_router(reflection.router, prefix="/api/reflection", tags=["reflection"])
app.include_router(thesis.router, prefix="/api/thesis", tags=["thesis"])
app.include_router(apps.router, prefix="/api/apps", tags=["apps"])
app.include_router(session.router, prefix="/api/session", tags=["session"])


@app.get("/")
def health():
    return {"status": "ok", "service": "zeitgeist"}
