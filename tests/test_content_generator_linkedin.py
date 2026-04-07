from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jinja2 import UndefinedError

from adapters.linkedin.content_generator import GeneratedPost, LinkedInContentGenerator
from marketmenow.models.project import BrandConfig, PersonaConfig


def _fake_settings() -> MagicMock:
    s = MagicMock()
    s.google_application_credentials = "fake.json"
    s.vertex_ai_project = "test-project"
    s.vertex_ai_location = "us-central1"
    return s


_BRAND = BrandConfig(
    name="Acme",
    url="https://acme.io",
    tagline="Ship faster",
    value_prop="Launch in days, not months",
    features=["CI/CD", "Auto-deploy"],
)

_PERSONA = PersonaConfig(
    name="founder",
    voice="Direct and practical",
    tone="Casual but knowledgeable",
)

_SAMPLE_RESPONSE = json.dumps(
    [
        {
            "type": "text_post",
            "body": "Hot take: CI/CD is table stakes now.",
            "hashtags": ["devops", "ci", "startup"],
        },
        {
            "type": "poll",
            "body": "",
            "hashtags": ["devops"],
            "poll_question": "Biggest deploy bottleneck?",
            "poll_options": ["Tests", "Approvals", "Infra"],
        },
    ]
)


class TestLinkedInContentGeneratorTemplateRendering:
    """generate_batch must render prompt templates with brand and persona context."""

    async def test_generate_batch_without_brand_raises(self) -> None:
        """Reproduces the 'brand' is undefined Jinja2 error."""
        with patch("adapters.linkedin.content_generator.create_llm_provider"):
            gen = LinkedInContentGenerator(_fake_settings())

        with pytest.raises(UndefinedError, match="brand"):
            await gen.generate_batch(count=2)

    async def test_generate_batch_with_brand_and_persona_succeeds(self) -> None:
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_RESPONSE

        with patch(
            "adapters.linkedin.content_generator.create_llm_provider"
        ) as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate_json = AsyncMock(return_value=mock_response)
            mock_provider_factory.return_value = mock_provider
            gen = LinkedInContentGenerator(_fake_settings())

        posts = await gen.generate_batch(count=2, brand=_BRAND, persona=_PERSONA)

        assert len(posts) == 2
        assert all(isinstance(p, GeneratedPost) for p in posts)

        call_kwargs = mock_provider.generate_json.call_args
        user_prompt = call_kwargs.kwargs["contents"]
        system_prompt = call_kwargs.kwargs["system"]

        assert "Acme" in user_prompt
        assert "Acme" in system_prompt
        assert "Direct and practical" in system_prompt

    async def test_generate_batch_renders_brand_features_in_system(self) -> None:
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_RESPONSE

        with patch(
            "adapters.linkedin.content_generator.create_llm_provider"
        ) as mock_provider_factory:
            mock_provider = MagicMock()
            mock_provider.generate_json = AsyncMock(return_value=mock_response)
            mock_provider_factory.return_value = mock_provider
            gen = LinkedInContentGenerator(_fake_settings())

        await gen.generate_batch(count=2, brand=_BRAND, persona=_PERSONA)

        call_kwargs = mock_provider.generate_json.call_args
        system_prompt = call_kwargs.kwargs["system"]

        assert "CI/CD" in system_prompt
        assert "Auto-deploy" in system_prompt
        assert "Launch in days, not months" in system_prompt
