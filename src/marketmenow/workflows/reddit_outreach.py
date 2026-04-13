from __future__ import annotations

from marketmenow.core.workflow import ParamDef, ParamType, Workflow
from marketmenow.steps.discover_reddit_outreach import DiscoverRedditOutreachStep
from marketmenow.steps.generate_outreach_comments import GenerateOutreachCommentsStep
from marketmenow.steps.post_outreach_comments import PostOutreachCommentsStep
from marketmenow.steps.score_post_relevance import ScorePostRelevanceStep

workflow = Workflow(
    name="reddit-outreach",
    description="Discover Reddit posts, score for product relevance, generate outreach comments, and post them.",
    steps=(
        DiscoverRedditOutreachStep(),
        ScorePostRelevanceStep(),
        GenerateOutreachCommentsStep(),
        PostOutreachCommentsStep(),
    ),
    params=(
        ParamDef(
            name="max-comments",
            type=ParamType.INT,
            default=10,
            help="Maximum number of outreach comments to post",
        ),
        ParamDef(
            name="min-score",
            type=ParamType.INT,
            default=0,
            help="Minimum relevance score (0-10) to qualify a post",
        ),
        ParamDef(
            name="dry-run",
            type=ParamType.BOOL,
            default=False,
            help="Discover, score, and generate comments but do not post",
        ),
    ),
)
