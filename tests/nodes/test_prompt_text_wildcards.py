from __future__ import annotations

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
    assert "wildcard generation" in seed_options["tooltip"]


def test_text_lm_input_types_expose_input_only_seed():
    input_types = TextLM.INPUT_TYPES()
    seed_type, seed_options = input_types["optional"]["seed"]

    assert seed_type == "INT"
    assert seed_options["forceInput"] is True
    assert "wildcard generation" in seed_options["tooltip"]
