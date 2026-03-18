from __future__ import annotations

import pytest

from adapters.instagram.reels.pipeline_steps import (
    StepRegistry,
    _resolve_inputs,
    create_default_registry,
)

# ---------------------------------------------------------------------------
# _resolve_inputs
# ---------------------------------------------------------------------------


class TestResolveInputs:
    def test_simple_variable_reference(self) -> None:
        result = _resolve_inputs(
            {"name": "{{ greeting }}"},
            {"greeting": "hello"},
        )
        assert result["name"] == "hello"

    def test_dotted_path(self) -> None:
        result = _resolve_inputs(
            {"val": "{{ data.score }}"},
            {"data": {"score": 95}},
        )
        assert result["val"] == 95

    def test_deep_dotted_path(self) -> None:
        result = _resolve_inputs(
            {"val": "{{ a.b.c }}"},
            {"a": {"b": {"c": "deep"}}},
        )
        assert result["val"] == "deep"

    def test_jinja_template_string(self) -> None:
        result = _resolve_inputs(
            {"msg": "Hello {{ name }}, score: {{ score }}"},
            {"name": "Alice", "score": "100"},
        )
        assert result["msg"] == "Hello Alice, score: 100"

    def test_nested_dicts(self) -> None:
        result = _resolve_inputs(
            {"outer": {"inner": "{{ val }}"}},
            {"val": "resolved"},
        )
        assert result["outer"]["inner"] == "resolved"

    def test_non_string_passthrough(self) -> None:
        result = _resolve_inputs(
            {"count": 42, "flag": True, "items": [1, 2, 3]},
            {},
        )
        assert result["count"] == 42
        assert result["flag"] is True
        assert result["items"] == [1, 2, 3]

    def test_missing_variable_fallback(self) -> None:
        result = _resolve_inputs(
            {"val": "{{ nonexistent }}"},
            {"other": "x"},
        )
        assert result["val"] == "{{ nonexistent }}"

    def test_missing_dotted_path_fallback(self) -> None:
        result = _resolve_inputs(
            {"val": "{{ a.missing }}"},
            {"a": {"b": 1}},
        )
        assert result["val"] == "{{ a.missing }}"

    def test_non_dict_in_dotted_path(self) -> None:
        result = _resolve_inputs(
            {"val": "{{ a.b.c }}"},
            {"a": {"b": "not_a_dict"}},
        )
        assert result["val"] == "{{ a.b.c }}"


# ---------------------------------------------------------------------------
# StepRegistry
# ---------------------------------------------------------------------------


class TestStepRegistry:
    def test_register_and_get(self) -> None:
        reg = StepRegistry()

        async def dummy(ctx, inputs):  # type: ignore[no-untyped-def]
            return "ok"

        reg.register("test_step", dummy)
        assert reg.get("test_step") is dummy

    def test_has(self) -> None:
        reg = StepRegistry()

        async def dummy(ctx, inputs):  # type: ignore[no-untyped-def]
            pass

        reg.register("exists", dummy)
        assert reg.has("exists") is True
        assert reg.has("missing") is False

    def test_get_missing_raises(self) -> None:
        reg = StepRegistry()
        with pytest.raises(KeyError, match="Unknown pipeline step type"):
            reg.get("nonexistent")


class TestDefaultRegistry:
    def test_has_built_in_steps(self) -> None:
        reg = create_default_registry()
        assert reg.has("rubric")
        assert reg.has("grading")
        assert reg.has("llm")
