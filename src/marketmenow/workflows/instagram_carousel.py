from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.generate_carousel import GenerateCarouselStep
from marketmenow.steps.package_capsule import PackageCapsuleStep
from marketmenow.steps.post_to_platform import PostToPlatformStep

workflow = Workflow(
    name="instagram-carousel",
    description="Generate an AI carousel (Gemini + Imagen) and post to Instagram.",
    steps=(
        GenerateCarouselStep(),
        PackageCapsuleStep(),
        PostToPlatformStep(platform="instagram"),
    ),
    params=(ParamDef(name="output_dir", type=ParamType.PATH, help="Output directory"),),
)
