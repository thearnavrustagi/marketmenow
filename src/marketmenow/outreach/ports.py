from __future__ import annotations

from typing import Protocol, runtime_checkable

from marketmenow.outreach.models import (
    DiscoveredProspectPost,
    OutreachSendResult,
    UserProfile,
)


@runtime_checkable
class DiscoveryVector(Protocol):
    """A single discovery strategy that finds prospect posts on a platform."""

    @property
    def name(self) -> str: ...

    async def discover(self) -> list[DiscoveredProspectPost]: ...


@runtime_checkable
class ProfileEnricher(Protocol):
    """Visits a user's profile and extracts structured data."""

    async def enrich(
        self,
        handle: str,
        triggering_posts: list[DiscoveredProspectPost],
    ) -> UserProfile | None: ...


@runtime_checkable
class MessageSender(Protocol):
    """Sends an outreach message to a handle on a specific platform."""

    async def send(self, handle: str, message: str) -> OutreachSendResult: ...
