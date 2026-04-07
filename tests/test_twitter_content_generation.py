from __future__ import annotations

import json

from conftest import MockLLMProvider
from marketmenow.models.project import BrandConfig, PersonaConfig

_THREAD_JSON = json.dumps(
    {
        "topic": "AI in education",
        "tweets": [
            {
                "position": 1,
                "text": "AI is transforming education. Here is how (thread):",
                "is_hook": True,
                "is_cta": False,
            },
            {
                "position": 2,
                "text": "First, personalized learning paths adapt to each student.",
                "is_hook": False,
                "is_cta": False,
            },
            {
                "position": 3,
                "text": "Second, automated grading frees up teacher time.",
                "is_hook": False,
                "is_cta": False,
            },
            {
                "position": 4,
                "text": "Third, AI tutors are available 24/7 for struggling students.",
                "is_hook": False,
                "is_cta": False,
            },
            {
                "position": 5,
                "text": "Fourth, content creation is being democratized.",
                "is_hook": False,
                "is_cta": False,
            },
            {
                "position": 6,
                "text": "Fifth, accessibility tools powered by AI help everyone.",
                "is_hook": False,
                "is_cta": False,
            },
            {
                "position": 7,
                "text": "Want to see AI in education in action? Follow for more.",
                "is_hook": False,
                "is_cta": True,
            },
        ],
    }
)


class TestThreadGeneration:
    async def test_thread_generation_json(self) -> None:
        """ThreadGenerator with mock provider returns a GeneratedThread with 7 tweets."""
        provider = MockLLMProvider(json_response=_THREAD_JSON)

        from adapters.twitter.thread_generator import ThreadGenerator

        gen = ThreadGenerator(
            provider=provider,
            brand=BrandConfig(name="TestBrand", url="https://test.com", tagline="Test"),
            persona=PersonaConfig(name="default", voice="casual", tone="friendly"),
        )
        thread = await gen.generate_thread(topic_hint="AI in education")

        assert thread.topic == "AI in education"
        assert len(thread.tweets) == 7
        assert thread.tweets[0].is_hook is True
        assert thread.tweets[6].is_cta is True

    async def test_thread_generator_uses_provider(self) -> None:
        """Verify the mock's calls list shows generate_json was called."""
        provider = MockLLMProvider(json_response=_THREAD_JSON)

        from adapters.twitter.thread_generator import ThreadGenerator

        gen = ThreadGenerator(
            provider=provider,
            brand=BrandConfig(name="TestBrand", url="https://test.com", tagline="Test"),
            persona=PersonaConfig(name="default", voice="casual", tone="friendly"),
        )
        await gen.generate_thread(topic_hint="AI in education")

        assert len(provider.calls) == 1
        assert provider.calls[0]["method"] == "generate_json"
