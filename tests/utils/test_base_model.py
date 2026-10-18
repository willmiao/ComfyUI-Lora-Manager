"""Unit tests for base-model architecture-family relations."""

from py.utils.base_model import (
    RELATION_COMPATIBLE,
    RELATION_INCOMPATIBLE,
    RELATION_SAME,
    RELATION_UNKNOWN,
    base_model_relation,
)


def test_identical_labels_are_same():
    assert base_model_relation("SDXL 1.0", "sdxl 1.0") == RELATION_SAME
    assert base_model_relation(" Pony ", "pony") == RELATION_SAME


def test_sdxl_lineage_is_compatible():
    assert base_model_relation("Pony", "Illustrious") == RELATION_COMPATIBLE
    assert base_model_relation("Illustrious", "SDXL 1.0") == RELATION_COMPATIBLE
    assert base_model_relation("NoobAI", "SDXL Lightning") == RELATION_COMPATIBLE


def test_sd1_lineage_is_compatible():
    assert base_model_relation("SD 1.5", "SD 1.4") == RELATION_COMPATIBLE
    assert base_model_relation("SD 1.5 LCM", "SD 1.5") == RELATION_COMPATIBLE


def test_flux1_lineage_is_compatible():
    assert base_model_relation("Flux.1 D", "Flux.1 S") == RELATION_COMPATIBLE


def test_cross_architecture_is_incompatible():
    assert base_model_relation("SD 1.5", "SDXL 1.0") == RELATION_INCOMPATIBLE
    assert base_model_relation("Pony", "Flux.1 D") == RELATION_INCOMPATIBLE


def test_pony_v7_is_not_sdxl_compatible():
    # Pony V7 is AuraFlow-based; sharing a name prefix with Pony means nothing.
    assert base_model_relation("Pony", "Pony V7") == RELATION_INCOMPATIBLE


def test_unknown_labels_stay_unknown():
    assert base_model_relation("", "SDXL 1.0") == RELATION_UNKNOWN
    assert base_model_relation("SDXL 1.0", "unknown") == RELATION_UNKNOWN
    assert base_model_relation(None, None) == RELATION_UNKNOWN


def test_unlisted_labels_fall_back_to_strict():
    # A label missing from the family table only matches itself exactly —
    # unknown new CivitAI labels must never be wrongly waved through.
    assert base_model_relation("Wan Video", "Wan Video") == RELATION_SAME
    assert base_model_relation("Wan Video", "Hunyuan Video") == RELATION_INCOMPATIBLE
    assert base_model_relation("Wan Video", "Pony") == RELATION_INCOMPATIBLE
