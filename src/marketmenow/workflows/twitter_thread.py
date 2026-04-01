from __future__ import annotations

from marketmenow.core.workflow import ParamDef, Workflow
from marketmenow.steps.generate_thread import GenerateThreadStep
from marketmenow.steps.package_capsule import PackageCapsuleStep
from marketmenow.steps.post_to_platform import PostToPlatformStep

workflow = Workflow(
    name="twitter-thread",
    description="Generate a viral Twitter/X thread via AI and post it.",
    steps=(
        GenerateThreadStep(),
        PackageCapsuleStep(),
        PostToPlatformStep(platform="twitter"),
    ),
    params=(
        ParamDef(
            name="topic",
            short="-t",
            help="Topic hint for the thread (leave empty for random)",
        ),
    ),
)
