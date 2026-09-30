"""JusticeFlow TZ API.  Run:  uvicorn app.main:app --reload   (from backend/)"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import settings
from .db import init_db
from .routers import admin, auth, cases, oversight, review


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="JusticeFlow TZ", version="0.2.0", lifespan=lifespan,
              description="Read-only decision-support overlay: case-delay risk and cause-list optimisation.")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, cases, review, oversight, admin):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
