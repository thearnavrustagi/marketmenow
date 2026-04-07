from __future__ import annotations

import json

from conftest import MockLLMProvider


class TestReelScriptGeneration:
    async def test_reel_script_json_structure(self) -> None:
        """Mock LLM provider returns valid reel script JSON and is called with generate_json."""
        reel_script = {
            "reaction_text": "Wait, what?!",
            "roast_text": "This code is a crime against humanity.",
            "brand_response": "Try our AI code reviewer.",
            "rubric_narration": "Let me grade this disaster.",
            "grading_narration": "F minus. Absolute F minus.",
            "result_comment": "Sometimes the best code is no code.",
        }
        provider = MockLLMProvider(json_response=json.dumps(reel_script))

        response = await provider.generate_json(
            model="gemini-2.5-flash",
            system="You are a reel script writer.",
            contents="Write a reel script about bad code.",
        )

        parsed = json.loads(response.text)
        assert parsed["reaction_text"] == "Wait, what?!"
        assert parsed["roast_text"] == "This code is a crime against humanity."
        assert parsed["brand_response"] == "Try our AI code reviewer."
        assert parsed["rubric_narration"] == "Let me grade this disaster."
        assert parsed["grading_narration"] == "F minus. Absolute F minus."
        assert parsed["result_comment"] == "Sometimes the best code is no code."

        assert len(provider.calls) == 1
        assert provider.calls[0]["method"] == "generate_json"

    async def test_reel_script_empty_response_handling(self) -> None:
        """Empty JSON response from LLM should not crash."""
        provider = MockLLMProvider(json_response="{}")

        response = await provider.generate_json(
            model="gemini-2.5-flash",
            system="You are a reel script writer.",
            contents="Write a reel script.",
        )

        parsed = json.loads(response.text)
        assert parsed == {}
        assert len(provider.calls) == 1
