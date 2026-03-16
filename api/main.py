from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from api.routers import runs, topics, opportunities, reflection, thesis, apps, session, telemetry, evals, simulator

app = FastAPI(title="Zeitgeist API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://zeitgeist.vercel.app",
        "https://zeitgeist-web.vercel.app",
        "https://zeitgeist-qeyd.onrender.com",
    ],
    allow_origin_regex=r"https://zeitgeist.*\.vercel\.app",
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
app.include_router(telemetry.router, prefix="/api/telemetry", tags=["telemetry"])
app.include_router(evals.router, prefix="/api/evals", tags=["evals"])
app.include_router(simulator.router, prefix="/api/simulator", tags=["simulator"])


@app.get("/")
def health():
    return {"status": "ok", "service": "zeitgeist"}
