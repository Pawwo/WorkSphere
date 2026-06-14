"""Legacy facade — use InboxService."""

from __future__ import annotations

from typing import Optional

from app.config import Settings, get_settings
from app.models.jobs import FitFilter, SeenJobUpdate, StatusFilter
from app.services.inbox_service import InboxService


class JobsService:
    def __init__(self, settings: Optional[Settings] = None):
        self._inbox = InboxService(settings or get_settings())

    def list_jobs(
        self,
        *,
        status: StatusFilter = None,
        fit: FitFilter = None,
        new_only: bool = False,
    ) -> dict:
        return self._inbox.list_jobs(status=status, fit=fit, new_only=new_only)

    def present_new_matches(self) -> dict:
        return self._inbox.present_new_matches()

    def update_job(self, url: str, update: SeenJobUpdate) -> bool:
        return self._inbox.update_job(url, update)
