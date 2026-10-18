"""Tests for the recipe import_info helpers (no-LoRA reason computation)."""

from py.services.recipes.import_info import (
    CHANNEL_BATCH_IMPORT_LOCAL,
    CHANNEL_BATCH_IMPORT_URL,
    CHANNEL_LOCAL,
    CHANNEL_REIMPORT_URL,
    CHANNEL_UPLOAD,
    CHANNEL_URL,
    CHANNEL_WIDGET,
    REASON_API_META_MISSING,
    REASON_API_NO_LORA_RESOURCES,
    REASON_METADATA_UNSUPPORTED,
    REASON_NO_EMBEDDED_METADATA,
    REASON_NO_LORAS_USED,
    REASON_VIDEO_NO_METADATA,
    REASON_WORKFLOW_METADATA_LIMITED,
    build_import_info,
    compute_no_loras_reason,
)


class TestComputeNoLorasReason:
    def test_video_takes_priority(self):
        diag = {"is_video": True, "exif_parser": "ComfyMetadataParser"}
        assert (
            compute_no_loras_reason(CHANNEL_BATCH_IMPORT_URL, diag)
            == REASON_VIDEO_NO_METADATA
        )

    def test_comfy_workflow_parser(self):
        diag = {"exif_parser": "ComfyMetadataParser", "exif_present": True}
        assert (
            compute_no_loras_reason(CHANNEL_UPLOAD, diag)
            == REASON_WORKFLOW_METADATA_LIMITED
        )

    def test_merged_comfy_parser(self):
        # ComfyUI workflow parsed from the merged dict (no string EXIF).
        diag = {"parser": "ComfyMetadataParser"}
        assert (
            compute_no_loras_reason(CHANNEL_LOCAL, diag)
            == REASON_WORKFLOW_METADATA_LIMITED
        )

    def test_civitai_url_with_api_meta_but_no_lora_resources(self):
        diag = {
            "civitai_image": True,
            "api_meta_keys": ["prompt"],
            "api_model_version_ids": 0,
            "exif_present": False,
        }
        assert (
            compute_no_loras_reason(CHANNEL_BATCH_IMPORT_URL, diag)
            == REASON_API_NO_LORA_RESOURCES
        )

    def test_civitai_url_with_model_version_ids_only(self):
        diag = {
            "civitai_image": True,
            "api_meta_keys": [],
            "api_model_version_ids": 2,
            "exif_present": False,
        }
        assert (
            compute_no_loras_reason(CHANNEL_URL, diag)
            == REASON_API_NO_LORA_RESOURCES
        )

    def test_civitai_url_with_no_meta_at_all(self):
        diag = {
            "civitai_image": True,
            "api_meta_keys": [],
            "api_model_version_ids": 0,
            "exif_present": False,
        }
        assert (
            compute_no_loras_reason(CHANNEL_REIMPORT_URL, diag)
            == REASON_API_META_MISSING
        )

    def test_civitai_url_with_parsed_exif_still_reports_api_gap(self):
        # CivitAI's onsite generator writes A1111-style EXIF WITHOUT LoRA
        # references (LoRA usage lives in CivitAI-internal data), so cleanly
        # parsed EXIF must NOT be read as "no LoRAs were used".
        diag = {
            "civitai_image": True,
            "api_meta_keys": ["prompt", "steps", "seed", "resources"],
            "api_model_version_ids": 1,
            "exif_present": True,
            "exif_parser": "AutomaticMetadataParser",
            "parser": "CivitaiApiMetadataParser",
        }
        assert (
            compute_no_loras_reason(CHANNEL_BATCH_IMPORT_URL, diag)
            == REASON_API_NO_LORA_RESOURCES
        )

    def test_generic_url_without_embedded_metadata(self):
        diag = {"civitai_image": False, "exif_present": False}
        assert (
            compute_no_loras_reason(CHANNEL_URL, diag) == REASON_NO_EMBEDDED_METADATA
        )

    def test_generic_url_with_unsupported_metadata(self):
        diag = {"civitai_image": False, "exif_present": True}
        assert (
            compute_no_loras_reason(CHANNEL_URL, diag) == REASON_METADATA_UNSUPPORTED
        )

    def test_generic_url_with_parsed_metadata_means_no_loras(self):
        diag = {
            "civitai_image": False,
            "exif_present": True,
            "exif_parser": "AutomaticMetadataParser",
        }
        assert compute_no_loras_reason(CHANNEL_URL, diag) == REASON_NO_LORAS_USED

    def test_widget(self):
        assert compute_no_loras_reason(CHANNEL_WIDGET, None) == REASON_NO_LORAS_USED

    def test_local_without_embedded_metadata(self):
        diag = {"exif_present": False}
        assert (
            compute_no_loras_reason(CHANNEL_LOCAL, diag)
            == REASON_NO_EMBEDDED_METADATA
        )
        assert (
            compute_no_loras_reason(CHANNEL_BATCH_IMPORT_LOCAL, diag)
            == REASON_NO_EMBEDDED_METADATA
        )

    def test_local_with_unsupported_metadata(self):
        diag = {"exif_present": True}
        assert (
            compute_no_loras_reason(CHANNEL_UPLOAD, diag)
            == REASON_METADATA_UNSUPPORTED
        )

    def test_missing_diagnostics_falls_back_safely(self):
        assert (
            compute_no_loras_reason(CHANNEL_LOCAL, None)
            == REASON_NO_EMBEDDED_METADATA
        )
        # URL channel without diagnostics is treated as a generic URL (the
        # civitai_image flag defaults to False).
        assert (
            compute_no_loras_reason(CHANNEL_URL, None)
            == REASON_NO_EMBEDDED_METADATA
        )


class TestBuildImportInfo:
    def test_channel_always_recorded(self):
        info = build_import_info(
            CHANNEL_URL, None, loras=[{"file_name": "x", "hash": "abc"}]
        )
        assert info == {"channel": CHANNEL_URL}

    def test_reason_and_details_when_no_loras(self):
        diag = {
            "civitai_image": True,
            "api_meta_keys": ["prompt"],
            "api_model_version_ids": 0,
            "exif_present": False,
            "exif_parser": None,
        }
        info = build_import_info(CHANNEL_BATCH_IMPORT_URL, diag, loras=[])
        assert info["channel"] == CHANNEL_BATCH_IMPORT_URL
        assert info["reason"] == REASON_API_NO_LORA_RESOURCES
        assert info["details"]["api_meta_keys"] == ["prompt"]
        assert info["details"]["api_model_version_ids"] == 0
        assert info["details"]["exif_present"] is False
        # Empty exif_parser must not leak into details.
        assert "exif_parser" not in info["details"]

    def test_details_omitted_when_nothing_to_report(self):
        info = build_import_info(CHANNEL_WIDGET, None, loras=[])
        assert info == {"channel": CHANNEL_WIDGET, "reason": REASON_NO_LORAS_USED}

    def test_api_meta_keys_capped(self):
        diag = {
            "civitai_image": True,
            "api_meta_keys": [f"k{i}" for i in range(50)],
            "api_model_version_ids": 1,
        }
        info = build_import_info(CHANNEL_URL, diag, loras=[])
        assert len(info["details"]["api_meta_keys"]) == 12
