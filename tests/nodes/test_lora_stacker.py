from py.nodes.lora_stacker import LoraStackerLM


def test_stacker_trigger_words_are_prompt_ready(monkeypatch):
    trigger_groups = {
        "stylemix": ["stylemix"],
        "character": ["@P4100"],
        "detail": ["detail one, detail two"],
    }
    monkeypatch.setattr(
        "py.nodes.lora_stacker.get_lora_info",
        lambda name: (f"/models/{name}.safetensors", trigger_groups[name]),
    )

    _, trigger_words, _ = LoraStackerLM().stack_loras(
        "",
        {
            "__value__": [
                {"active": True, "name": name, "strength": 1.0}
                for name in trigger_groups
            ]
        },
    )

    assert trigger_words == "stylemix, @P4100, detail one, detail two"
