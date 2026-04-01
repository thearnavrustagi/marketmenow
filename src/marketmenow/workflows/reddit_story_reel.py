from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.generate_reel import GenerateReelStep
from marketmenow.steps.package_capsule import PackageCapsuleStep
from marketmenow.steps.post_to_platform import PostToPlatformStep

workflow = Workflow(
    name="reddit-story-reel",
    description="Generate a Reddit horror story reel with background video and post to Instagram.",
    steps=(
        GenerateReelStep(),
        PackageCapsuleStep(),
        PostToPlatformStep(platform="instagram"),
    ),
    params=(
        ParamDef(
            name="template",
            default="reddit_horror_story",
            help="Reel template ID",
        ),
        ParamDef(name="tts", help="TTS provider: elevenlabs, openai, local, or kokoro"),
        ParamDef(name="caption", help="Reel caption (overrides generated caption)"),
        ParamDef(name="hashtags", help="Comma-separated hashtags"),
        ParamDef(name="output_dir", type=ParamType.PATH, help="Output directory"),
        ParamDef(
            name="dry_run",
            type=ParamType.BOOL,
            default=False,
            help="Generate reel without publishing to Instagram",
        ),
    ),
)
