from __future__ import annotations

from marketmenow.core.workflow import ParamDef, Workflow
from marketmenow.steps.post_from_capsule import PostFromCapsuleStep

workflow = Workflow(
    name="post-capsule",
    description="Post an existing content capsule to any platform.",
    steps=(PostFromCapsuleStep(),),
    params=(
        ParamDef(name="capsule", required=True, help="Capsule ID to post"),
        ParamDef(name="platform", required=True, help="Target platform (e.g. youtube, tiktok)"),
        ParamDef(name="privacy", help="Privacy status: public, unlisted, or private"),
    ),
)
