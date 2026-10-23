"""Regression tests for recipe saving from tiled VAE decode workflows (#1158).

``VAEDecodeTiled`` is a native decoder that returns ``(images,)`` just like
``VAEDecode``. Its output must be captured for recipe previews both when it
executes and when ComfyUI serves it from cache instead of re-executing it.
"""

from types import SimpleNamespace

from py.metadata_collector.constants import IMAGES


def _register_node(monkeypatch, class_name):
    """Register a fake node class the way ComfyUI's NODE_CLASS_MAPPINGS does."""
    import nodes

    node_cls = type(class_name, (), {})
    monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, class_name, node_cls)
    return node_cls


def _start_prompt(registry, prompt_id, class_name, node_id="decode"):
    graph = {node_id: {"class_type": class_name, "inputs": {}}}
    registry.start_collection(prompt_id)
    registry.set_current_prompt(SimpleNamespace(original_prompt=graph))
    return graph


def _execute_decode(registry, node_id, class_name, image):
    """Mimic the execution hooks recording then updating a decode node."""
    registry.record_node_execution(node_id, class_name, {"samples": ["sampler", 0]}, None)
    # ``_map_node_over_list`` returns one result tuple per input; VAEDecode and
    # VAEDecodeTiled both return ``(images,)``.
    registry.update_node_execution(node_id, class_name, [(image,)])


def test_vaedecode_tiled_output_is_captured(metadata_registry, monkeypatch):
    _register_node(monkeypatch, "VAEDecodeTiled")
    image = object()

    # Subgraph-style ids are strings, not ints; they must work too.
    _start_prompt(metadata_registry, "prompt-tiled", "VAEDecodeTiled", node_id="12:34")
    _execute_decode(metadata_registry, "12:34", "VAEDecodeTiled", image)

    metadata = metadata_registry.get_metadata("prompt-tiled")
    assert metadata[IMAGES]["first_decode"]["node_id"] == "12:34"
    assert metadata_registry.get_first_decoded_image("prompt-tiled") == (image,)


def test_vaedecode_tiled_cache_hit_returns_cached_image(metadata_registry, monkeypatch):
    _register_node(monkeypatch, "VAEDecodeTiled")
    image = object()

    graph = _start_prompt(metadata_registry, "prompt-first", "VAEDecodeTiled")
    _execute_decode(metadata_registry, "decode", "VAEDecodeTiled", image)

    # The next run reuses the cached decode node, so no execution hook fires.
    metadata_registry.start_collection("prompt-cached")
    metadata_registry.set_current_prompt(SimpleNamespace(original_prompt=graph))

    assert metadata_registry.get_first_decoded_image("prompt-cached") == (image,)


def test_unrelated_image_node_is_not_used_for_recipe(metadata_registry, monkeypatch):
    _register_node(monkeypatch, "LoadImage")

    _start_prompt(metadata_registry, "prompt-load", "LoadImage", node_id="load")
    metadata_registry.record_node_execution(
        "load", "LoadImage", {"image": "photo.png"}, None
    )
    metadata_registry.update_node_execution("load", "LoadImage", [(object(),)])

    assert metadata_registry.get_first_decoded_image("prompt-load") is None


def test_first_decode_wins_between_decoder_variants(metadata_registry, monkeypatch):
    _register_node(monkeypatch, "VAEDecode")
    _register_node(monkeypatch, "VAEDecodeTiled")
    first_image = object()
    later_image = object()

    graph = {
        "decode": {"class_type": "VAEDecode", "inputs": {}},
        "decode_tiled": {"class_type": "VAEDecodeTiled", "inputs": {}},
    }
    metadata_registry.start_collection("prompt-mixed")
    metadata_registry.set_current_prompt(SimpleNamespace(original_prompt=graph))

    _execute_decode(metadata_registry, "decode", "VAEDecode", first_image)
    _execute_decode(metadata_registry, "decode_tiled", "VAEDecodeTiled", later_image)

    assert metadata_registry.get_first_decoded_image("prompt-mixed") == (first_image,)
