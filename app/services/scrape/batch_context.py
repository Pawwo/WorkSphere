"""Shared seen_jobs state for scrape_batch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.services.scrape.dedup import identity_keys_from_seen, job_identity
from app.storage.files import load_tracker_keys
from app.storage.job_repository import JobRepository

if TYPE_CHECKING:
    from app.config import Settings
    from app.models.jobs import SeenJobEntry


class BatchContext:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.repo = JobRepository(settings.seen_jobs_path)
        self.seen: dict[str, SeenJobEntry] = self.repo.all()
        self.known_identities: set[tuple[str, str]] = identity_keys_from_seen(self.seen)
        for company_l, title_l in load_tracker_keys(settings.tracker_path):
            ident = job_identity(company_l, title_l)
            if ident:
                self.known_identities.add(ident)
        self._lock = asyncio.Lock()
        self.rocketjobs_timeouts = 0
        self.rocketjobs_circuit_open = False
        self.praca_pl_timeouts = 0
        self.praca_pl_circuit_open = False

    def record_rocketjobs_timeout(self) -> None:
        self.rocketjobs_timeouts += 1
        if self.rocketjobs_timeouts >= 3:
            self.rocketjobs_circuit_open = True

    def record_praca_pl_timeout(self) -> None:
        self.praca_pl_timeouts += 1
        if self.praca_pl_timeouts >= 2:
            self.praca_pl_circuit_open = True

    async def flush(self) -> None:
        async with self._lock:
            self.repo.flush()
