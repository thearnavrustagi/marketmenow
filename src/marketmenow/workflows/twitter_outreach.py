from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.discover_prospects import DiscoverProspectsStep
from marketmenow.steps.enrich_profiles import EnrichProfilesStep
from marketmenow.steps.generate_messages import GenerateMessagesStep
from marketmenow.steps.score_prospects import ScoreProspectsStep
from marketmenow.steps.send_messages import SendMessagesStep

workflow = Workflow(
    name="twitter-outreach",
    description="Discover, evaluate, and cold-DM prospects on Twitter/X using project config.",
    steps=(
        DiscoverProspectsStep(platform="twitter"),
        EnrichProfilesStep(platform="twitter"),
        ScoreProspectsStep(),
        GenerateMessagesStep(),
        SendMessagesStep(platform="twitter"),
    ),
    params=(
        ParamDef(
            name="max-messages",
            type=ParamType.INT,
            default=10,
            help="Maximum number of messages to send",
        ),
        ParamDef(
            name="min-score",
            type=ParamType.INT,
            default=0,
            help="Minimum relevance score (0-10) to qualify a prospect",
        ),
        ParamDef(
            name="dry-run",
            type=ParamType.BOOL,
            default=False,
            help="Discover, score, and generate messages but do not send",
        ),
        ParamDef(
            name="headless",
            type=ParamType.BOOL,
            default=True,
            help="Run the browser in headless mode",
        ),
    ),
)
