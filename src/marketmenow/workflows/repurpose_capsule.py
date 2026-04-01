from __future__ import annotations

from marketmenow.core.workflow import ParamDef, Workflow
from marketmenow.steps.repurpose_content import RepurposeContentStep

workflow = Workflow(
    name="repurpose-capsule",
    description="Repurpose an existing capsule's content for a different platform and format.",
    steps=(RepurposeContentStep(),),
    params=(
        ParamDef(name="capsule", required=True, help="Source capsule ID to repurpose"),
        ParamDef(
            name="platform", required=True, help="Target platform (e.g. twitter, linkedin, reddit)"
        ),
        ParamDef(
            name="target-modality",
            help="Target format: thread, text_post, or direct_message (auto-detected from platform if omitted)",
        ),
    ),
)
