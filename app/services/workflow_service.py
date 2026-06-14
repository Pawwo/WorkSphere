"""Legacy facade — use InboxService."""

from __future__ import annotations

from typing import Optional

from app.config import Settings, get_settings
from app.models.jobs import FitFilter, StatusFilter, TierFilter
from app.services.inbox_service import InboxService
from app.services.workflow.triage import score_job, salary_triage_penalty

__all__ = [
    "WorkflowService",
    "score_job",
    "salary_triage_penalty",
    "STRONG_KEYWORDS",
    "GOOD_KEYWORDS",
    "REJECT_KEYWORDS",
]

# Re-export for backward compatibility
from app.services.keyword_triage import REJECT_KEYWORDS  # noqa: E402
from app.services.workflow.triage import (  # noqa: E402
    GOOD_KEYWORDS,
    STRONG_KEYWORDS,
)


class WorkflowService:
    def __init__(self, settings: Optional[Settings] = None):
        self._inbox = InboxService(settings or get_settings())
        self.settings = self._inbox.settings

    @property
    def triage_path(self):
        return self._inbox.triage_path

    @property
    def queue_path(self):
        return self._inbox.queue_path

    def get_counts(self) -> dict:
        return self._inbox.get_counts()

    def get_evaluate_queue(self) -> dict:
        return self._inbox.get_evaluate_queue()

    def load_inbox(
        self,
        *,
        tier: TierFilter = None,
        status: StatusFilter = None,
        fit: FitFilter = None,
        q: str | None = None,
    ) -> dict:
        return self._inbox.load_inbox(tier=tier, status=status, fit=fit, q=q)

    def sync_job_to_triage(self, url: str, *, status: str) -> None:
        self._inbox.sync_job_to_triage(url, status=status)

    def run_triage(self) -> dict:
        return self._inbox.run_triage()
