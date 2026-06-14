"""Build system context for the assistant prompt."""

from __future__ import annotations

from typing import Optional

from app.config import Settings, get_settings
from app.services.inbox_service import InboxService
from app.services.profile_service import ProfileService


class ContextBuilder:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def snapshot(self) -> dict:
        inbox = InboxService(self.settings).get_counts()
        profile = ProfileService(self.settings).get_status()
        return {
            "inbox_counts": inbox,
            "profile_complete": profile.get("complete"),
            "profile_sections": profile.get("sections_done", []),
            "placeholders_remaining": profile.get("placeholders_remaining", 0),
        }
