"""FastAPI entrypoint for the plain HTML/CSS/JS Newser dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src import web_services

BASE_DIR = Path(__file__).resolve().parent
REFRESH_JOB_ID = "feed_refresh"


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    web_services.initialize()
    scheduler = create_scheduler()
    scheduler.start()
    app_instance.state.scheduler = scheduler
    web_services.ensure_feed_refresh(background=True)
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=web_services.BRIEF_TIMEZONE)
    scheduler.add_job(
        web_services.ensure_feed_refresh,
        trigger=IntervalTrigger(minutes=30, timezone=web_services.BRIEF_TIMEZONE),
        id=REFRESH_JOB_ID,
        kwargs={"background": True},
        max_instances=1,
        replace_existing=True,
    )
    return scheduler


app = FastAPI(title="Newser Web", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")


@app.get("/")
def index(request: Request):
    minimum, maximum = web_services.date_bounds()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sources": web_services.SOURCES,
            "areas": web_services.AREAS,
            "min_date": minimum.isoformat(),
            "max_date": maximum.isoformat(),
        },
    )


@app.get("/api/feed")
def api_feed(
    fecha: str | None = None,
    fuentes: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    orden: str = "Puntaje",
    q: str | None = None,
):
    return web_services.get_feed(fecha=fecha, fuentes=fuentes, areas=areas, orden=orden, q=q)


@app.get("/api/brief")
def api_brief(fecha: str | None = None):
    return web_services.get_brief(fecha)


@app.get("/api/daily-briefs")
def api_daily_briefs():
    return web_services.get_past_daily_briefs()


@app.get("/api/stats")
def api_stats():
    return web_services.get_stats()


@app.get("/api/refresh-status")
def api_refresh_status(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    next_check_at = None
    if scheduler:
        job = scheduler.get_job(REFRESH_JOB_ID)
        next_check_at = job.next_run_time if job else None
    return web_services.get_refresh_status(next_check_at)


@app.get("/api/search/suggestions")
def api_search_suggestions(
    q: str,
    fecha: str | None = None,
    fuentes: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
):
    return {"suggestions": web_services.get_suggestions(q, fecha=fecha, fuentes=fuentes, areas=areas)}


@app.post("/api/articles/{article_id}/summary")
def api_generate_summary(article_id: str):
    result = web_services.generate_summary(article_id)
    status_code = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status_code)


@app.post("/api/refresh")
def api_refresh():
    result = web_services.refresh_feed()
    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)
