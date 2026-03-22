from __future__ import annotations

import yaml

from marketmenow.core.project_templates import (
    generate_outreach_campaign,
    generate_reddit_prompt,
    generate_reddit_targets,
    generate_reel_meta_prompt,
    generate_twitter_prompt,
    generate_twitter_targets,
)
from marketmenow.models.project import BrandConfig, PersonaConfig, TargetCustomer


def _brand() -> BrandConfig:
    return BrandConfig(
        name="TestBrand",
        url="testbrand.io",
        tagline="A test product",
        value_prop="Best tests ever",
        features=["fast", "reliable"],
    )

def _persona() -> PersonaConfig:
    return PersonaConfig(
        name="default",
        description="The sarcastic tester",
        voice="confident, witty",
        tone="casual, funny",
        example_phrases=["ngl", "lowkey"],
    )

def _customer() -> TargetCustomer:
    return TargetCustomer(
        description="Developers who need tests",
        pain_points=["slow CI", "flaky tests"],
        keywords=["testing", "CI/CD"],
        platforms=["twitter", "reddit"],
    )


class TestGenerateTwitterPrompt:
    def test_contains_brand_name(self):
        result = generate_twitter_prompt(_brand(), _persona())
        assert "TestBrand" in result

    def test_contains_persona_voice(self):
        result = generate_twitter_prompt(_brand(), _persona())
        assert "confident" in result.lower() or "witty" in result.lower()

    def test_valid_yaml(self):
        result = generate_twitter_prompt(_brand(), _persona())
        data = yaml.safe_load(result)
        assert "system" in data
        assert "user" in data

    def test_has_template_variables(self):
        result = generate_twitter_prompt(_brand(), _persona())
        assert "{{ author_handle }}" in result or "{{author_handle}}" in result


class TestGenerateRedditPrompt:
    def test_contains_brand_name(self):
        result = generate_reddit_prompt(_brand(), _persona())
        assert "TestBrand" in result or "testbrand" in result.lower()

    def test_valid_yaml(self):
        result = generate_reddit_prompt(_brand(), _persona())
        data = yaml.safe_load(result)
        assert "system" in data
        assert "user" in data


class TestGenerateTargets:
    def test_twitter_targets_valid_yaml(self):
        result = generate_twitter_targets(
            ["@user1", "@user2"], ["#hash1"], ["@company1"]
        )
        data = yaml.safe_load(result)
        assert "influencers" in data
        assert "@user1" in data["influencers"]

    def test_reddit_targets_valid_yaml(self):
        result = generate_reddit_targets(["Cooking", "recipes"], ["meal prep"])
        data = yaml.safe_load(result)
        assert "subreddits" in data
        assert "Cooking" in data["subreddits"]


class TestGenerateOutreachCampaign:
    def test_contains_product_info(self):
        result = generate_outreach_campaign(
            _brand(), _customer(),
            [{"name": "Fit", "description": "Role fit", "max_points": 3}],
            [{"type": "pain_search", "entries": ["testing pain"], "max_per_entry": 5}],
            {"tone": "casual", "max_messages": 10, "max_message_length": 280},
        )
        assert "TestBrand" in result

    def test_valid_yaml(self):
        result = generate_outreach_campaign(
            _brand(), _customer(),
            [{"name": "Fit", "description": "Role fit", "max_points": 3}],
            [{"type": "pain_search", "entries": ["testing pain"], "max_per_entry": 5}],
            {"tone": "casual", "max_messages": 10, "max_message_length": 280},
        )
        data = yaml.safe_load(result)
        assert "product" in data
        assert "ideal_customer" in data


class TestGenerateReelMetaPrompt:
    def test_contains_brand_fields(self):
        result = generate_reel_meta_prompt(_brand(), _customer())
        assert "TestBrand" in result

    def test_contains_instructions(self):
        result = generate_reel_meta_prompt(_brand(), _customer())
        assert "REEL CONCEPT" in result or "reel" in result.lower()
