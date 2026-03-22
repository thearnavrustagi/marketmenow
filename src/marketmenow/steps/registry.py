from __future__ import annotations

from dataclasses import dataclass

from marketmenow.steps.discover_posts import DiscoverPostsStep
from marketmenow.steps.discover_prospects import DiscoverProspectsStep
from marketmenow.steps.enrich_profiles import EnrichProfilesStep
from marketmenow.steps.generate_carousel import GenerateCarouselStep
from marketmenow.steps.generate_messages import GenerateMessagesStep
from marketmenow.steps.generate_reddit_post import GenerateRedditPostStep
from marketmenow.steps.generate_reel import GenerateReelStep
from marketmenow.steps.generate_replies import GenerateRepliesStep
from marketmenow.steps.generate_thread import GenerateThreadStep
from marketmenow.steps.linkedin_post import LinkedInPostStep
from marketmenow.steps.post_replies import PostRepliesStep
from marketmenow.steps.post_to_platform import PostToPlatformStep
from marketmenow.steps.post_to_subreddits import PostToSubredditsStep
from marketmenow.steps.score_prospects import ScoreProspectsStep
from marketmenow.steps.send_emails import SendEmailsStep
from marketmenow.steps.send_messages import SendMessagesStep
from marketmenow.steps.youtube_upload import YouTubeUploadStep


@dataclass(frozen=True)
class StepInfo:
    name: str
    description: str
    cls: type


_STEP_CLASSES: dict[str, type] = {
    "generate-reel": GenerateReelStep,
    "generate-carousel": GenerateCarouselStep,
    "generate-thread": GenerateThreadStep,
    "generate-reddit-posts": GenerateRedditPostStep,
    "generate-replies": GenerateRepliesStep,
    "post-to-platform": PostToPlatformStep,
    "post-to-subreddits": PostToSubredditsStep,
    "post-replies": PostRepliesStep,
    "discover-posts": DiscoverPostsStep,
    "discover-prospects": DiscoverProspectsStep,
    "enrich-profiles": EnrichProfilesStep,
    "score-prospects": ScoreProspectsStep,
    "generate-messages": GenerateMessagesStep,
    "send-messages": SendMessagesStep,
    "linkedin-post": LinkedInPostStep,
    "send-emails": SendEmailsStep,
    "youtube-upload": YouTubeUploadStep,
}


def get_step_class(name: str) -> type:
    """Return the step class for a given step name."""
    if name not in _STEP_CLASSES:
        raise KeyError(f"Unknown step: {name}")
    return _STEP_CLASSES[name]


def list_steps() -> list[StepInfo]:
    """Return metadata for all registered steps."""
    result: list[StepInfo] = []
    for name, cls in _STEP_CLASSES.items():
        instance = cls() if not _needs_args(cls) else None
        desc = instance.description if instance else cls.__doc__ or ""
        if isinstance(desc, str):
            desc = desc.strip().split("\n")[0]
        result.append(StepInfo(name=name, description=desc, cls=cls))
    return result


def _needs_args(cls: type) -> bool:
    """Check if __init__ requires arguments beyond self."""
    import inspect

    sig = inspect.signature(cls.__init__)
    params = [
        p
        for p in sig.parameters.values()
        if p.name != "self" and p.default is inspect.Parameter.empty
    ]
    return len(params) > 0
