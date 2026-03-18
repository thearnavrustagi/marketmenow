from __future__ import annotations


class MarketMeNowError(Exception):
    """Base exception for all framework errors."""


class AdapterNotFoundError(MarketMeNowError):
    def __init__(self, platform: str) -> None:
        super().__init__(f"No adapter registered for platform: {platform}")
        self.platform = platform


class UnsupportedModalityError(MarketMeNowError):
    def __init__(self, platform: str, modality: str) -> None:
        super().__init__(f"Platform '{platform}' does not support modality '{modality}'")
        self.platform = platform
        self.modality = modality


class AuthenticationError(MarketMeNowError):
    def __init__(self, platform: str, reason: str = "") -> None:
        super().__init__(f"Authentication failed for '{platform}': {reason}")
        self.platform = platform


class PublishError(MarketMeNowError):
    def __init__(self, platform: str, reason: str = "") -> None:
        super().__init__(f"Publish failed on '{platform}': {reason}")
        self.platform = platform


class RenderError(MarketMeNowError):
    def __init__(self, platform: str, reason: str = "") -> None:
        super().__init__(f"Render failed for '{platform}': {reason}")
        self.platform = platform


class UploadError(MarketMeNowError):
    def __init__(self, platform: str, reason: str = "") -> None:
        super().__init__(f"Upload failed on '{platform}': {reason}")
        self.platform = platform
