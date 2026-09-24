from __future__ import annotations

from typing import Any, cast

from py.nodes.prompt import PromptLM
from py.nodes.text import TextLM


def test_text_lm_expands_wildcards_before_output(monkeypatch):
    node = TextLM()

    expand_calls = []

    class StubService:
        def expand_text(self, text, seed=None):
            expand_calls.append((text, seed))
            return "expanded text"

    monkeypatch.setattr("py.nodes.text.get_wildcard_service", lambda: StubService())

    assert node.process("__flower__", seed=9) == ("expanded text",)
    assert expand_calls == [("__flower__", 9)]


def test_prompt_lm_expands_before_appending_trigger_words(monkeypatch):
    node = PromptLM()

    class StubService:
        def expand_text(self, text, seed=None):
            assert text == "__flower__"
            assert seed == 42
            return "rose"

    class StubEncoder:
        def encode(self, clip, prompt):
            assert clip == "clip"
            assert prompt == "artist style, rose"
            return ("conditioning",)

    monkeypatch.setattr("py.nodes.prompt.get_wildcard_service", lambda: StubService())
    monkeypatch.setattr("nodes.CLIPTextEncode", lambda: StubEncoder(), raising=False)

    result = node.encode("__flower__", "clip", seed=42, trigger_words1="artist style")

    assert result == ("conditioning", "artist style, rose")


def test_prompt_lm_input_types_expose_input_only_seed():
    input_types = PromptLM.INPUT_TYPES()
    seed_type, seed_options = input_types["optional"]["seed"]

    assert seed_type == "INT"
    assert seed_options["forceInput"] is True
    assert "wildcard generation" in cast(Any, seed_options)["tooltip"]


def test_text_lm_input_types_expose_input_only_seed():
    input_types = TextLM.INPUT_TYPES()
    seed_type, seed_options = input_types["optional"]["seed"]

    assert seed_type == "INT"
    assert seed_options["forceInput"] is True
    assert "wildcard generation" in cast(Any, seed_options)["tooltip"]


def test_text_lm_is_changed_forces_rerun_without_seed_when_text_is_dynamic():
    result = TextLM.IS_CHANGED("__flower__", seed=None)

    assert result != result


def test_text_lm_is_changed_keeps_cache_for_seeded_or_static_text():
    assert TextLM.IS_CHANGED("__flower__", seed=7) is False
    assert TextLM.IS_CHANGED("plain text", seed=None) is False
    assert TextLM.IS_CHANGED("{red|blue}", seed=7) is False


def test_prompt_lm_is_changed_forces_rerun_without_seed_when_text_is_dynamic():
    result = PromptLM.IS_CHANGED("{red|blue}", clip="clip", seed=None)

    assert result != result


def test_prompt_lm_is_changed_keeps_cache_for_seeded_or_static_text():
    assert PromptLM.IS_CHANGED("__flower__", clip="clip", seed=11) is False
    assert PromptLM.IS_CHANGED("plain text", clip="clip", seed=None) is False


def _linked_prompt(upstream_inputs):
    return {
        "1": {"class_type": "TextMultiline", "inputs": upstream_inputs},
        "2": {
            "class_type": "PromptLM",
            "inputs": {"text": ["1", 0], "clip": ["3", 0]},
        },
    }


def test_prompt_lm_is_changed_forces_rerun_for_linked_dynamic_text():
    prompt = _linked_prompt({"text": "{red|blue|green}"})

    result = PromptLM.IS_CHANGED(None, clip="clip", seed=None, prompt=prompt, unique_id="2")

    assert result != result


def test_prompt_lm_is_changed_keeps_cache_for_linked_static_text():
    prompt = _linked_prompt({"text": "a plain static prompt"})

    assert PromptLM.IS_CHANGED(None, clip="clip", seed=None, prompt=prompt, unique_id="2") is False
    assert PromptLM.IS_CHANGED(None, clip="clip", seed=5, prompt=prompt, unique_id="2") is False


def test_prompt_lm_is_changed_forces_rerun_when_linked_text_unresolvable():
    chained = _linked_prompt({"text": ["9", 0]})

    result = PromptLM.IS_CHANGED(None, clip="clip", seed=None, prompt=chained, unique_id="2")

    assert result != result
    assert PromptLM.IS_CHANGED(None, clip="clip", seed=None, prompt=None, unique_id="2") != 0
    missing_upstream = _linked_prompt({"text": "static"})
    missing_upstream["2"]["inputs"]["text"] = ["99", 0]
    assert (
        PromptLM.IS_CHANGED(None, clip="clip", seed=None, prompt=missing_upstream, unique_id="2")
        != 0
    )


def test_text_lm_is_changed_forces_rerun_for_linked_dynamic_text():
    prompt = _linked_prompt({"text": "__flower__"})

    result = TextLM.IS_CHANGED(None, seed=None, prompt=prompt, unique_id="2")

    assert result != result


def test_text_lm_is_changed_keeps_cache_for_linked_static_text():
    prompt = _linked_prompt({"text": "a plain static prompt"})

    assert TextLM.IS_CHANGED(None, seed=None, prompt=prompt, unique_id="2") is False


def test_text_lm_process_accepts_hidden_inputs(monkeypatch):
    node = TextLM()

    class StubService:
        def expand_text(self, text, seed=None):
            return text

    monkeypatch.setattr("py.nodes.text.get_wildcard_service", lambda: StubService())

    assert node.process("hello", seed=None, prompt={}, unique_id="2") == ("hello",)


def test_prompt_lm_encode_accepts_hidden_inputs(monkeypatch):
    node = PromptLM()

    class StubService:
        def expand_text(self, text, seed=None):
            return text

    class StubEncoder:
        def encode(self, clip, prompt):
            return ("conditioning",)

    monkeypatch.setattr("py.nodes.prompt.get_wildcard_service", lambda: StubService())
    monkeypatch.setattr("nodes.CLIPTextEncode", lambda: StubEncoder(), raising=False)

    result = node.encode("hello", "clip", seed=None, prompt={}, unique_id="2")

    assert result == ("conditioning", "hello")


def test_prompt_lm_input_types_declare_hidden_prompt_inputs():
    hidden = PromptLM.INPUT_TYPES()["hidden"]

    assert hidden == {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}


def test_text_lm_input_types_declare_hidden_prompt_inputs():
    hidden = TextLM.INPUT_TYPES()["hidden"]

    assert hidden == {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}
