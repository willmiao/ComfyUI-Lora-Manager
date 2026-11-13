import pytest

from py.nodes.lora_trigger_words import LoraTriggerWordsLM


def test_trigger_words_resolver_preserves_order_and_groups(monkeypatch):
    resolved_names = []

    def resolve(name):
        resolved_names.append(name)
        groups = {
            "folder/alpha": ["alpha one, alpha two", "alpha alternate"],
            "beta": ["beta trigger"],
        }
        return f"/models/{name}.safetensors", groups[name]

    monkeypatch.setattr("py.nodes.lora_trigger_words.get_lora_info_absolute", resolve)
    node = LoraTriggerWordsLM()

    result = node.resolve(
        "<lora:folder/alpha:0.8:0.6> <lora:beta:1.0>"
    )

    assert result == (
        "alpha one, alpha two,, alpha alternate,, beta trigger",
    )
    assert resolved_names == ["folder/alpha", "beta"]


@pytest.mark.parametrize("lora_syntax", ["", "   ", "no LoRA tags"])
def test_trigger_words_resolver_returns_empty_for_no_entries(lora_syntax):
    assert LoraTriggerWordsLM().resolve(lora_syntax) == ("",)


def test_trigger_words_resolver_skips_failed_lookups(monkeypatch):
    def resolve(name):
        if name == "broken":
            raise RuntimeError("lookup failed")
        return f"/models/{name}.safetensors", [f"{name} trigger"]

    monkeypatch.setattr("py.nodes.lora_trigger_words.get_lora_info_absolute", resolve)

    assert LoraTriggerWordsLM().resolve(
        "<lora:broken:1> <lora:working:1>"
    ) == ("working trigger",)
