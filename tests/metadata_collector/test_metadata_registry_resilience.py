"""Registry caching must survive a failing node extractor."""

import logging

from py.metadata_collector.constants import IMAGES, SAMPLING
from py.metadata_collector.node_extractors import NODE_EXTRACTORS


class _PartiallyFailingExtractor:
    """Writes one category, then fails, like the YuE2 latent-shape crash."""

    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        metadata[SAMPLING][node_id] = {
            "parameters": {"seed": 1},
            "node_id": node_id,
            "is_sampler": True,
        }
        raise RuntimeError("extractor exploded")

    @staticmethod
    def update(node_id, outputs, metadata):
        metadata[IMAGES][node_id] = {"image": outputs}
        raise RuntimeError("extractor exploded")


class _EarlyFailingExtractor:
    @staticmethod
    def extract(node_id, inputs, outputs, metadata):
        raise RuntimeError("extractor exploded")


def test_record_node_execution_caches_partial_metadata(
    metadata_registry, monkeypatch, caplog
):
    monkeypatch.setitem(
        NODE_EXTRACTORS, "ExplodingNodeForTest", _PartiallyFailingExtractor
    )
    metadata_registry.start_collection("prompt-resilience")

    with caplog.at_level(
        logging.ERROR, logger="py.metadata_collector.metadata_registry"
    ):
        metadata_registry.record_node_execution(
            "1", "ExplodingNodeForTest", {"seed": 1}, None
        )

    cached = metadata_registry.node_cache["1:ExplodingNodeForTest"]
    assert cached[SAMPLING]["1"]["parameters"] == {"seed": 1}
    assert "Metadata extraction failed" in caplog.text


def test_record_node_execution_keeps_previous_cache_when_nothing_was_collected(
    metadata_registry, monkeypatch
):
    monkeypatch.setitem(
        NODE_EXTRACTORS, "EarlyFailingNodeForTest", _EarlyFailingExtractor
    )
    metadata_registry.start_collection("prompt-resilience")
    previous = {SAMPLING: {"2": {"parameters": {"seed": 7}, "node_id": "2"}}}
    metadata_registry.node_cache["2:EarlyFailingNodeForTest"] = previous

    metadata_registry.record_node_execution("2", "EarlyFailingNodeForTest", {}, None)

    assert metadata_registry.node_cache["2:EarlyFailingNodeForTest"] is previous


def test_update_node_execution_caches_partial_metadata(
    metadata_registry, monkeypatch
):
    monkeypatch.setitem(
        NODE_EXTRACTORS, "ExplodingNodeForTest", _PartiallyFailingExtractor
    )
    metadata_registry.start_collection("prompt-resilience")

    metadata_registry.update_node_execution(
        "3", "ExplodingNodeForTest", {"image": "data"}
    )

    cached = metadata_registry.node_cache["3:ExplodingNodeForTest"]
    assert cached[IMAGES]["3"] == {"image": {"image": "data"}}
