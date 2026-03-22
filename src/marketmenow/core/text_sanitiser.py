from __future__ import annotations

from marketmenow.normaliser import NormalisedContent

EM_DASH = "\u2014"
EN_DASH = "\u2013"


def _sanitise_str(text: str) -> str:
    return text.replace(EM_DASH, "-").replace(EN_DASH, "-")


def _sanitise_extra(extra: dict[str, object]) -> dict[str, object]:
    """Recursively replace dashes in string and list-of-string values."""
    cleaned: dict[str, object] = {}
    for key, value in extra.items():
        if isinstance(value, str):
            cleaned[key] = _sanitise_str(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _sanitise_str(item) if isinstance(item, str) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def sanitise_text(content: NormalisedContent) -> NormalisedContent:
    """Strip em-dashes and en-dashes from every text field.

    Runs after the renderer so all platform-specific text is finalised.
    AI detectors flag em-dashes as synthetic; replacing with hyphens avoids that.
    """
    return content.model_copy(
        update={
            "text_segments": [_sanitise_str(s) for s in content.text_segments],
            "subject": _sanitise_str(content.subject) if content.subject else content.subject,
            "hashtags": [_sanitise_str(h) for h in content.hashtags],
            "extra": _sanitise_extra(content.extra),
        },
    )
