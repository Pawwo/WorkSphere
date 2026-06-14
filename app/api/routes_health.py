from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.llm.client import BielikClient
from app.models.jobs import HealthStatus
from app.scrapers.bun_cli import BunCLIWrapper
from app.search.searxng_client import SearXNGClient
from app.services.latex_service import LatexService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health():
    llm = await BielikClient().healthcheck_extended()
    searxng = await SearXNGClient().healthcheck()
    scrapers = await BunCLIWrapper().healthcheck()
    settings = get_settings()
    latex = LatexService(settings.repo_root, settings=settings).tools_available()
    latex_required = settings.cv_renderer.lower() == "latex"
    latex_ok = (
        latex.get("lualatex") and latex.get("xelatex")
        if latex_required
        else True
    )

    llm_idle = llm.get("status") == "idle"
    models_ok = llm.get("models_ok", llm.get("ok"))
    inference_ok = llm.get("inference_ok")
    overall = "ok"
    if (
        (not llm.get("ok") and not llm_idle)
        or not searxng.get("ok")
        or not scrapers.get("ok")
        or (latex_required and not latex_ok)
    ):
        overall = "degraded"
    if models_ok and inference_ok is False:
        overall = "degraded"
    if not llm.get("ok") and not llm_idle and not scrapers.get("ok"):
        overall = "error"

    return HealthStatus(
        status=overall,  # type: ignore[arg-type]
        llm=llm,
        searxng=searxng,
        scrapers=scrapers,
        latex={**latex, "ok": latex_ok, "required": latex_required},
    )
