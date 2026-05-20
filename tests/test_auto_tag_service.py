import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from services.auto_tag_service import extract_auto_tags, AUTO_TAG_CATEGORIES


class TestExtractAutoTags:
    def test_file_name_high_i2v(self):
        result = extract_auto_tags({
            "file_name": "Shirt_lift_Wan2.2_14B_I2V_HIGH_v1.0",
            "base_model": "Wan Video 2.2 I2V-A14B",
            "civitai": {},
        })
        assert set(result) == {"HIGH", "I2V"}

    def test_file_name_t2v_low(self):
        result = extract_auto_tags({
            "file_name": "my_wan_t2v_low_v2",
            "base_model": "Wan 2.1",
            "civitai": {},
        })
        assert set(result) == {"LOW", "T2V"}

    def test_file_name_ti2v_high(self):
        result = extract_auto_tags({
            "file_name": "wan_ti2v_high_quality",
            "base_model": "Wan 2.2",
            "civitai": {},
        })
        assert set(result) == {"HIGH", "TI2V"}

    def test_file_name_lightning_turbo(self):
        result = extract_auto_tags({
            "file_name": "sdxl_lightning_turbo_v3",
            "base_model": "SDXL",
            "civitai": {},
        })
        assert set(result) == {"Lightning", "Turbo"}

    def test_base_model_source(self):
        result = extract_auto_tags({
            "file_name": "my_lora_v1",
            "base_model": "Wan Video 2.2 I2V-A14B",
            "civitai": {},
        })
        assert "I2V" in result

    def test_civitai_name_source(self):
        result = extract_auto_tags({
            "file_name": "model_v1",
            "base_model": "Wan",
            "civitai": {"name": "HIGH Quality"},
        })
        assert "HIGH" in result

    def test_no_false_match_flow(self):
        result = extract_auto_tags({
            "file_name": "flux_dev_model",
            "base_model": "Flux.1 D",
            "civitai": {},
        })
        assert "LOW" not in result

    def test_no_false_match_glow(self):
        result = extract_auto_tags({
            "file_name": "glow_style_lora",
            "base_model": "SDXL",
            "civitai": {},
        })
        assert "LOW" not in result

    def test_high_low_only_for_wan(self):
        """HIGH/LOW should not appear for non-Wan models even in filename."""
        result = extract_auto_tags({
            "file_name": "my_model_high_quality_v2",
            "base_model": "Flux.1 D",
            "civitai": {"name": "HIGH"},
        })
        assert "HIGH" not in result
        assert "LOW" not in result

    def test_no_distilled(self):
        result = extract_auto_tags({
            "file_name": "ltx-2.3-22b-distilled-lora-384",
            "base_model": "LTXV 2.3",
            "civitai": {},
        })
        assert result == []

    def test_empty(self):
        result = extract_auto_tags({
            "file_name": "generic_lora_v1",
            "base_model": "SDXL",
            "civitai": {},
        })
        assert result == []

    def test_missing_fields(self):
        result = extract_auto_tags({})
        assert result == []

    def test_dash_separated(self):
        result = extract_auto_tags({
            "file_name": "wan-i2v-high-v2",
            "base_model": "Wan 2.2",
            "civitai": {},
        })
        assert set(result) == {"HIGH", "I2V"}

    def test_dot_separated(self):
        result = extract_auto_tags({
            "file_name": "wan.i2v.high.v2",
            "base_model": "Wan 2.2",
            "civitai": {},
        })
        assert set(result) == {"HIGH", "I2V"}

    def test_case_insensitive(self):
        result = extract_auto_tags({
            "file_name": "WAN_i2v_High",
            "base_model": "Wan 2.2",
            "civitai": {},
        })
        assert set(result) == {"HIGH", "I2V"}

    # ── Layer 2: user-defined tags as manual fallback ───────────

    def test_user_tags_fallback_when_detection_fails(self):
        result = extract_auto_tags({
            "file_name": "BOTH-v1.0",
            "base_model": "Wan 2.2",
            "civitai": {},
            "tags": ["HIGH", "I2V", "T2V"],
        })
        assert set(result) == {"HIGH", "I2V", "T2V"}

    def test_user_tags_augment_partial_detection(self):
        result = extract_auto_tags({
            "file_name": "wan_i2v_hn_v2",
            "base_model": "Wan 2.2 I2V",
            "civitai": {},
            "tags": ["HIGH"],
        })
        assert set(result) == {"HIGH", "I2V"}

    def test_user_tags_non_auto_tag_ignored(self):
        result = extract_auto_tags({
            "file_name": "model_v1",
            "base_model": "Wan 2.2",
            "civitai": {},
            "tags": ["HIGH", "character", "style", "nsfw"],
        })
        assert set(result) == {"HIGH"}

    def test_user_tags_overrides_non_wan_gate(self):
        result = extract_auto_tags({
            "file_name": "flux_model_v1",
            "base_model": "Flux.1 D",
            "civitai": {},
            "tags": ["HIGH", "LOW", "Turbo"],
        })
        assert set(result) == {"HIGH", "LOW", "Turbo"}

    def test_user_tags_no_duplication(self):
        result = extract_auto_tags({
            "file_name": "wan_i2v_high_v3",
            "base_model": "Wan 2.2",
            "civitai": {},
            "tags": ["HIGH", "I2V"],
        })
        assert set(result) == {"HIGH", "I2V"}

    def test_user_tags_lightning_turbo_manual(self):
        result = extract_auto_tags({
            "file_name": "sdxl_model_v1",
            "base_model": "SDXL",
            "civitai": {},
            "tags": ["Lightning"],
        })
        assert set(result) == {"Lightning"}

    def test_user_tags_case_insensitive_lowercase(self):
        result = extract_auto_tags({
            "file_name": "wan_masterpieces_v2",
            "base_model": "Wan Video 14B t2v",
            "civitai": {},
            "tags": ["high"],
        })
        assert set(result) == {"HIGH", "T2V"}

    def test_user_tags_case_insensitive_mixed(self):
        result = extract_auto_tags({
            "file_name": "model_v1",
            "base_model": "SDXL",
            "civitai": {},
            "tags": ["lightning", "turbo", "i2v"],
        })
        assert set(result) == {"Lightning", "Turbo", "I2V"}


class TestAutoTagCategories:
    def test_all_patterns_compile(self):
        import re
        for label, pattern in AUTO_TAG_CATEGORIES.items():
            re.compile(pattern, re.IGNORECASE)

    def test_mode_group_tags(self):
        from services.auto_tag_service import MODE_TAGS
        assert "HIGH" in MODE_TAGS
        assert "LOW" in MODE_TAGS

    def test_video_group_tags(self):
        from services.auto_tag_service import VIDEO_MODE_TAGS
        assert "I2V" in VIDEO_MODE_TAGS
        assert "T2V" in VIDEO_MODE_TAGS
        assert "TI2V" in VIDEO_MODE_TAGS

    def test_default_enabled_groups(self):
        from services.auto_tag_service import DEFAULT_ENABLED_GROUPS
        assert "mode" in DEFAULT_ENABLED_GROUPS
        assert "video" in DEFAULT_ENABLED_GROUPS
        assert "speed" not in DEFAULT_ENABLED_GROUPS
