from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.discover_prospects import DiscoverProspectsStep
from marketmenow.steps.enrich_profiles import EnrichProfilesStep
from marketmenow.steps.generate_messages import GenerateMessagesStep
from marketmenow.steps.score_prospects import ScoreProspectsStep
from marketmenow.steps.send_messages import SendMessagesStep

workflow = Workflow(
    name="twitter-outreach",
    description="Discover, evaluate, and cold-DM prospects on Twitter/X based on a customer profile rubric.",
    steps=(
        DiscoverProspectsStep(platform="twitter"),
        EnrichProfilesStep(platform="twitter"),
        ScoreProspectsStep(),
        GenerateMessagesStep(),
        SendMessagesStep(platform="twitter"),
    ),
    params=(
        ParamDef(
            name="profile",
            type=ParamType.PATH,
            required=True,
            help="Path to customer profile YAML",
        ),
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
            help="Override minimum rubric score from the profile YAML",
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
