from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.generate_reel import GenerateReelStep
from marketmenow.steps.package_capsule import PackageCapsuleStep
from marketmenow.steps.post_to_platform import PostToPlatformStep

workflow = Workflow(
    name="instagram-reel",
    description="Generate a reel from a YAML template and post to Instagram.",
    steps=(
        GenerateReelStep(),
        PackageCapsuleStep(),
        PostToPlatformStep(platform="instagram"),
    ),
    params=(
        ParamDef(name="template", default="can_ai_grade_this", help="Reel template ID"),
        ParamDef(name="tts", help="TTS provider: elevenlabs, openai, local, or kokoro"),
        ParamDef(name="assignment", type=ParamType.PATH, help="Path to assignment image"),
        ParamDef(name="rubric", type=ParamType.PATH, help="Path to rubric YAML/JSON file"),
        ParamDef(name="caption", help="Reel caption"),
        ParamDef(name="hashtags", help="Comma-separated hashtags"),
        ParamDef(name="output_dir", type=ParamType.PATH, help="Output directory"),
        ParamDef(name="comment_username", help="Username for the TikTok-style comment hook"),
        ParamDef(name="comment_text", help="Comment text for the TikTok hook"),
        ParamDef(name="student_name", help="Student name on the grading card"),
    ),
)
