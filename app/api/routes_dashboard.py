from __future__ import annotations

from fastapi import APIRouter

from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard():
    return await DashboardService().summary()
