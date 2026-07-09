"""FastAPI entrypoint for the plain HTML/CSS/JS Newser dashboard."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
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
SERVERLESS_RUNTIME = os.getenv("VERCEL") == "1"
_APP_INITIALIZED = False
_APP_INITIALIZE_LOCK = threading.Lock()
SOURCE_LINKS = {
    "GitHub Trending": "https://github.com/trending",
    "Hacker News": "https://news.ycombinator.com/",
    "Reuters": "https://www.reuters.com/technology/",
    "GitHub Blog": "https://github.blog/",
    "OpenAI Blog": "https://openai.com/news/",
    "Hugging Face Blog": "https://huggingface.co/blog",
}


def ensure_app_initialized() -> None:
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return
    with _APP_INITIALIZE_LOCK:
        if _APP_INITIALIZED:
            return
        web_services.initialize()
        _APP_INITIALIZED = True


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    ensure_app_initialized()
    scheduler = None
    if not SERVERLESS_RUNTIME:
        scheduler = create_scheduler()
        scheduler.start()
        web_services.ensure_feed_refresh(background=True)
        web_services.ensure_daily_brief_catchup(background=True)
    app_instance.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=web_services.BRIEF_TIMEZONE)
    scheduler.add_job(
        web_services.ensure_feed_refresh,
        trigger=IntervalTrigger(hours=1, timezone=web_services.BRIEF_TIMEZONE),
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


app = FastAPI(title="Newser Web", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/assets", StaticFiles(directory=str(BASE_DIR / "assets")), name="assets")


@app.middleware("http")
async def initialize_before_request(request: Request, call_next):
    ensure_app_initialized()
    return await call_next(request)


@app.get("/")
def index(request: Request):
    minimum, maximum = web_services.date_bounds()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "sources": web_services.SOURCES,
            "source_links": SOURCE_LINKS,
            "areas": web_services.area_options("es"),
            "min_date": minimum.isoformat(),
            "max_date": maximum.isoformat(),
        },
    )


@app.get("/api/feed")
def api_feed(
    fecha: str | None = None,
    fuentes: Annotated[list[str] | None, Query()] = None,
    prioritized_fuentes: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    orden: str = "Puntaje",
    q: str | None = None,
    lang: str = "es",
):
    return web_services.get_feed(
        fecha=fecha,
        fuentes=fuentes,
        prioritized_fuentes=prioritized_fuentes,
        areas=areas,
        orden=orden,
        q=q,
        lang=lang,
    )


@app.get("/api/brief")
def api_brief(fecha: str | None = None, lang: str = "es"):
    return web_services.get_brief(fecha, lang=lang)


@app.get("/api/daily-briefs")
def api_daily_briefs(lang: str = "es"):
    return web_services.get_past_daily_briefs(lang=lang)


@app.get("/api/favorites")
def api_favorites(lang: str = "es"):
    return web_services.get_favorites(lang=lang)


@app.get("/api/stats")
def api_stats(lang: str = "es"):
    return web_services.get_stats(lang=lang)


@app.get("/api/refresh-status")
def api_refresh_status(request: Request, lang: str = "es"):
    scheduler = getattr(request.app.state, "scheduler", None)
    next_check_at = None
    if scheduler:
        job = scheduler.get_job(REFRESH_JOB_ID)
        next_check_at = job.next_run_time if job else None
    return web_services.get_refresh_status(next_check_at)


@app.get("/api/health")
def api_health(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    feed_job = scheduler.get_job(REFRESH_JOB_ID) if scheduler else None
    daily_job = scheduler.get_job(DAILY_BRIEF_JOB_ID) if scheduler else None
    next_check_at = feed_job.next_run_time if feed_job else None

    checks = {
        "database": True,
        "scheduler_running": SERVERLESS_RUNTIME or bool(scheduler and scheduler.running),
        "feed_refresh_job": SERVERLESS_RUNTIME or feed_job is not None,
        "daily_brief_job": SERVERLESS_RUNTIME or daily_job is not None,
    }
    errors: list[str] = []

    try:
        web_services.check_database_connection()
    except Exception as exc:
        checks["database"] = False
        errors.append(f"database: {exc}")

    refresh_status = web_services.get_refresh_status(next_check_at)
    if refresh_status.get("last_error"):
        errors.append(f"scheduler last_error: {refresh_status['last_error']}")

    ok = all(checks.values()) and not errors
    payload = {
        "ok": ok,
        "serverless_runtime": SERVERLESS_RUNTIME,
        "checks": checks,
        "refresh_status": refresh_status,
        "errors": errors,
    }
    return JSONResponse(payload, status_code=200 if ok else 503)


@app.get("/api/dynamic-keywords")
def api_dynamic_keywords():
    return web_services.get_dynamic_keywords()


@app.get("/api/search/suggestions")
def api_search_suggestions(
    q: str,
    fecha: str | None = None,
    fuentes: Annotated[list[str] | None, Query()] = None,
    areas: Annotated[list[str] | None, Query()] = None,
    lang: str = "es",
):
    return {"suggestions": web_services.get_suggestions(q, fecha=fecha, fuentes=fuentes, areas=areas, lang=lang)}


@app.post("/api/articles/{article_id}/summary")
def api_generate_summary(article_id: str, lang: str = "es"):
    result = web_services.generate_summary(article_id, lang=lang)
    status_code = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status_code)


@app.post("/api/articles/{article_id}/favorite")
def api_mark_favorite(article_id: str, lang: str = "es"):
    result = web_services.mark_favorite(article_id, lang=lang)
    status_code = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status_code)


@app.delete("/api/articles/{article_id}/favorite")
def api_remove_favorite(article_id: str, lang: str = "es"):
    result = web_services.remove_favorite(article_id, lang=lang)
    status_code = 200 if result.get("ok") else 404
    return JSONResponse(result, status_code=status_code)


@app.post("/api/refresh")
def api_refresh():
    result = web_services.refresh_feed()
    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)
