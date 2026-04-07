from __future__ import annotations

import pytest

from marketmenow.integrations.llm import LLMProvider, create_llm_provider


class TestCreateLLMProvider:
    def test_default_creates_gemini(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default provider (no LLM_PROVIDER) should create GeminiProvider."""
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "test")

        from marketmenow.integrations.providers.gemini import GeminiProvider

        provider = create_llm_provider()
        assert isinstance(provider, GeminiProvider)

    def test_openai_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM_PROVIDER=openai should attempt to create OpenAIProvider."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_LLM_API_KEY", "test")
        monkeypatch.setenv("OPENAI_API_KEY", "test")

        try:
            provider = create_llm_provider()
            from marketmenow.integrations.providers.openai import OpenAIProvider

            assert isinstance(provider, OpenAIProvider)
        except ImportError:
            pytest.skip("openai SDK not installed")

    def test_anthropic_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM_PROVIDER=anthropic should attempt to create AnthropicProvider."""
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

        try:
            provider = create_llm_provider()
            from marketmenow.integrations.providers.anthropic import AnthropicProvider

            assert isinstance(provider, AnthropicProvider)
        except ImportError:
            pytest.skip("anthropic SDK not installed")

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid LLM_PROVIDER should raise ValueError."""
        monkeypatch.setenv("LLM_PROVIDER", "invalid")

        with pytest.raises(ValueError, match="Unknown LLM_PROVIDER='invalid'"):
            create_llm_provider()

    def test_protocol_conformance(self, mock_provider: object) -> None:
        """MockLLMProvider should satisfy the LLMProvider protocol."""
        assert isinstance(mock_provider, LLMProvider)
