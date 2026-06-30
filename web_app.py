"""FastAPI entrypoint for the plain HTML/CSS/JS Newser dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src import web_services

BASE_DIR = Path(__file__).resolve().parent
REFRESH_JOB_ID = "feed_refresh"
DAILY_BRIEF_JOB_ID = "daily_brief"
DAILY_BRIEF_CATCHUP_JOB_ID = "daily_brief_catchup"


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    web_services.initialize()
    scheduler = create_scheduler()
    scheduler.start()
    app_instance.state.scheduler = scheduler
    web_services.ensure_feed_refresh(background=True)
    schedule_daily_brief_catchup(scheduler)
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
    scheduler.add_job(
        web_services.generate_daily_brief_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=web_services.BRIEF_TIMEZONE),
        id=DAILY_BRIEF_JOB_ID,
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    return scheduler


def schedule_daily_brief_catchup(scheduler: BackgroundScheduler) -> bool:
    if not web_services.should_catch_up_daily_brief():
        return False
    scheduler.add_job(
        web_services.generate_daily_brief_job,
        trigger=DateTrigger(run_date=datetime.now(web_services.BRIEF_TIMEZONE), timezone=web_services.BRIEF_TIMEZONE),
        id=DAILY_BRIEF_CATCHUP_JOB_ID,
        max_instances=1,
        replace_existing=True,
    )
    return True


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


@app.get("/api/favorites")
def api_favorites():
    return web_services.get_favorites()


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


@app.get("/api/dynamic-keywords")
def api_dynamic_keywords():
    return web_services.get_dynamic_keywords()


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


@app.post("/api/articles/{article_id}/favorite")
def api_mark_favorite(article_id: str):
    result = web_services.mark_favorite(article_id)
    status_code = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status_code)


@app.delete("/api/articles/{article_id}/favorite")
def api_remove_favorite(article_id: str):
    result = web_services.remove_favorite(article_id)
    status_code = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status_code)


@app.post("/api/refresh")
def api_refresh():
    result = web_services.refresh_feed()
    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)
