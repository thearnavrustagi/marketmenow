from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.fetch_feedback import FetchYouTubeFeedbackStep
from marketmenow.steps.generate_reel import GenerateReelStep
from marketmenow.steps.inject_reel_id import InjectReelIdStep
from marketmenow.steps.package_capsule import PackageCapsuleStep
from marketmenow.steps.prepare_youtube import PrepareYouTubeStep
from marketmenow.steps.youtube_upload import YouTubeUploadStep

workflow = Workflow(
    name="youtube-short-generate",
    description="Generate a reel from a template and publish as a YouTube Short.",
    steps=(
        FetchYouTubeFeedbackStep(),
        GenerateReelStep(),
        PackageCapsuleStep(),
        PrepareYouTubeStep(),
        InjectReelIdStep(),
        YouTubeUploadStep(),
    ),
    params=(
        ParamDef(name="template", default="can_ai_grade_this", help="Reel template ID"),
        ParamDef(name="tts", help="TTS provider: elevenlabs, openai, local, or kokoro"),
        ParamDef(name="assignment", type=ParamType.PATH, help="Path to assignment image"),
        ParamDef(name="rubric", type=ParamType.PATH, help="Path to rubric YAML/JSON file"),
        ParamDef(name="caption", help="Override caption"),
        ParamDef(name="hashtags", help="Override comma-separated hashtags"),
        ParamDef(name="output_dir", type=ParamType.PATH, help="Output directory"),
        ParamDef(name="comment_username", help="Username for the TikTok-style comment hook"),
        ParamDef(name="comment_text", help="Comment text for the TikTok hook"),
        ParamDef(name="student_name", help="Student name on the grading card"),
        ParamDef(name="privacy", help="Privacy status: public, unlisted, or private"),
        ParamDef(
            name="feedback_days",
            type=ParamType.INT,
            help="Days to look back for feedback (default: 7)",
        ),
    ),
)
