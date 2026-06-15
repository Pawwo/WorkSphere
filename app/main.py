from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_apply import router as apply_router
from app.api.routes_applications import router as applications_router
from app.api.routes_assistant import router as assistant_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_documents import router as documents_router
from app.api.routes_expand import router as expand_router
from app.api.routes_files import router as files_router
from app.api.routes_health import router as health_router
from app.api.routes_inbox import router as inbox_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_profile import router as profile_router
from app.api.routes_reset import router as reset_router
from app.api.routes_scrape import router as scrape_router
from app.api.routes_setup import router as setup_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_tools import router as tools_router
from app.api.routes_tracker import router as tracker_router
from app.api.routes_upskill import router as upskill_router
from app.api.routes_workflow import router as workflow_router
from app.config import get_settings
from app.ui.pages.application_page import application_page_html
from app.ui.pages.apply_page import apply_page_html
from app.ui.pages.dashboard_page import dashboard_page_html
from app.ui.pages.documents_page import documents_page_html
from app.ui.pages.inbox_page import inbox_page_html
from app.ui.pages.profile_page import profile_page_html
from app.ui.pages.scrape_page import scrape_page_html
from app.ui.pages.setup_page import setup_page_html
from app.ui.pages.tools_page import tools_page_html
from app.ui.pages.tracker_page import tracker_page_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.pipeline.apply_queue import recover_stale_apply_tasks, stale_task_watchdog_loop
    from app.llm.client import BielikClient
    from app.search.searxng_client import SearXNGClient

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.job_scraper_dir.mkdir(parents=True, exist_ok=True)
    logger.info("WorkSphere started — data dir: %s", settings.data_dir)

    llm = await BielikClient(settings).healthcheck_extended()
    if not llm.get("ok"):
        logger.warning(
            "LLM unreachable at %s — %s (see SETUP.md)",
            settings.llm_base_url,
            llm.get("error") or llm.get("status") or "connection failed",
        )
    searxng = await SearXNGClient(settings).healthcheck()
    if not searxng.get("ok"):
        logger.warning(
            "SearXNG unreachable at %s — expand/upskill degraded (deploy/searxng/setup.sh)",
            settings.searxng_base_url,
        )

    n = await recover_stale_apply_tasks(settings)
    if n:
        logger.info("Recovered %s stale apply task(s) on startup", n)
    watchdog = asyncio.create_task(stale_task_watchdog_loop(settings))
    yield
    watchdog.cancel()
    try:
        await watchdog
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="WorkSphere",
        description="Standalone job search assistant with Polish portal scrapers",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(tasks_router)
    app.include_router(documents_router)
    app.include_router(setup_router)
    app.include_router(profile_router)
    app.include_router(scrape_router)
    app.include_router(inbox_router)
    app.include_router(jobs_router)
    app.include_router(tracker_router)
    app.include_router(apply_router)
    app.include_router(applications_router)
    app.include_router(expand_router)
    app.include_router(upskill_router)
    app.include_router(tools_router)
    app.include_router(reset_router)
    app.include_router(files_router)
    app.include_router(workflow_router)
    app.include_router(assistant_router)

    @app.get("/")
    async def index():
        return RedirectResponse(url="/inbox", status_code=302)

    @app.get("/inbox", response_class=HTMLResponse)
    async def inbox_page():
        return inbox_page_html()

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page():
        return setup_page_html()

    @app.get("/apply", response_class=HTMLResponse)
    async def apply_page():
        return apply_page_html()

    @app.get("/applications/{app_id}", response_class=HTMLResponse)
    async def application_page(app_id: int):
        return application_page_html(app_id)

    @app.get("/jobs")
    async def jobs_redirect():
        return RedirectResponse(url="/inbox?view=table", status_code=302)

    @app.get("/documents", response_class=HTMLResponse)
    async def documents_page():
        return documents_page_html()

    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page():
        return profile_page_html()

    @app.get("/tracker", response_class=HTMLResponse)
    async def tracker_page():
        return tracker_page_html()

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page():
        return dashboard_page_html()

    @app.get("/scrape", response_class=HTMLResponse)
    async def scrape_page():
        return scrape_page_html()

    @app.get("/tools", response_class=HTMLResponse)
    async def tools_page():
        return tools_page_html()

    return app


app = create_app()
