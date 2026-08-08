"""Tests for model sub_type field refactoring."""

import pytest
from py.utils.models import (
    BaseModelMetadata,
    LoraMetadata,
    CheckpointMetadata,
    EmbeddingMetadata,
)


class TestCheckpointMetadataSubType:
    """Test CheckpointMetadata uses sub_type field."""

    def test_checkpoint_has_sub_type_field(self):
        """CheckpointMetadata should have sub_type field."""
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "checkpoint"

    def test_checkpoint_sub_type_can_be_diffusion_model(self):
        """CheckpointMetadata sub_type can be set to diffusion_model."""
        metadata = CheckpointMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
            sub_type="diffusion_model",
        )
        assert metadata.sub_type == "diffusion_model"

    def test_checkpoint_from_civitai_info_uses_sub_type(self):
        """from_civitai_info should use sub_type from version_info."""
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [{"name": "model.safetensors", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.safetensors"
        
        metadata = CheckpointMetadata.from_civitai_info(version_info, file_info, save_path)
        
        assert hasattr(metadata, "sub_type")
        # When type is missing from version_info, defaults to "checkpoint"
        assert metadata.sub_type == "checkpoint"


class TestEmbeddingMetadataSubType:
    """Test EmbeddingMetadata uses sub_type field."""

    def test_embedding_has_sub_type_field(self):
        """EmbeddingMetadata should have sub_type field."""
        metadata = EmbeddingMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.pt",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SD1.5",
            preview_url="",
        )
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "embedding"

    def test_embedding_from_civitai_info_uses_sub_type(self):
        """from_civitai_info should use sub_type from version_info."""
        version_info = {
            "baseModel": "SD1.5",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [{"name": "model.pt", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.pt"
        
        metadata = EmbeddingMetadata.from_civitai_info(version_info, file_info, save_path)
        
        assert hasattr(metadata, "sub_type")
        assert metadata.sub_type == "embedding"


class TestLoraMetadataConsistency:
    """Test LoraMetadata consistency (no sub_type field, uses civitai data)."""

    def test_lora_does_not_have_sub_type_field(self):
        """LoraMetadata should not have sub_type field (uses civitai.model.type)."""
        metadata = LoraMetadata(
            file_name="test",
            model_name="Test Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
        )
        # Lora doesn't have sub_type field - it uses civitai data
        assert not hasattr(metadata, "sub_type")

    def test_lora_from_civitai_info_extracts_type(self):
        """from_civitai_info should extract type from civitai data."""
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": [], "type": "Lora"},
            "files": [{"name": "model.safetensors", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}, "primary": True}],
        }
        file_info = version_info["files"][0]
        save_path = "/test/model.safetensors"
        
        metadata = LoraMetadata.from_civitai_info(version_info, file_info, save_path)
        
        # Type is stored in civitai dict
        assert metadata.civitai.get("model", {}).get("type") == "Lora"


class TestBaseModelMetadataAutov3:
    """Three-state autov3 semantics on BaseModelMetadata (None/''/12-hex)."""

    def _make_dict(self, **overrides):
        data = {
            "file_name": "model",
            "model_name": "Model",
            "file_path": "/tmp/model.safetensors",
            "size": 0,
            "modified": 0.0,
            "sha256": "deadbeef",
            "base_model": "Unknown",
            "preview_url": "",
        }
        data.update(overrides)
        return data

    def test_from_dict_null_autov3_normalizes_to_empty_string(self):
        metadata = BaseModelMetadata.from_dict(self._make_dict(autov3=None))

        assert metadata.autov3 == ""

    def test_to_dict_emits_autov3_null_when_checked_unavailable(self):
        metadata = BaseModelMetadata.from_dict(self._make_dict(autov3=None))

        payload = metadata.to_dict()

        assert "autov3" in payload
        assert payload["autov3"] is None

    def test_from_dict_absent_autov3_stays_none(self):
        metadata = BaseModelMetadata.from_dict(self._make_dict())

        assert metadata.autov3 is None

    def test_to_dict_omits_autov3_when_not_checked(self):
        metadata = BaseModelMetadata.from_dict(self._make_dict())

        assert "autov3" not in metadata.to_dict()

    def test_from_dict_preserves_lowercase_autov3_value(self):
        metadata = BaseModelMetadata.from_dict(self._make_dict(autov3="abcdef123456"))

        assert metadata.autov3 == "abcdef123456"
        assert metadata.to_dict()["autov3"] == "abcdef123456"

    @pytest.mark.parametrize("model_cls", [LoraMetadata, CheckpointMetadata, EmbeddingMetadata])
    def test_from_civitai_info_extracts_autov3(self, model_cls):
        # Civitai versions can ship multiple files; AutoV3 is taken from the
        # file whose SHA256 matches the downloaded file.
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [
                {"name": "other.safetensors", "sizeKB": 100, "hashes": {"SHA256": "zzz999"}},
                {
                    "name": "model.safetensors",
                    "sizeKB": 1000,
                    "hashes": {"SHA256": "abc123", "AutoV3": "ABCDEF1234567890ABCDEF"},
                },
            ],
        }
        file_info = {
            "name": "model.safetensors",
            "sizeKB": 1000,
            "hashes": {"SHA256": "abc123"},
        }

        metadata = model_cls.from_civitai_info(version_info, file_info, "/test/model.safetensors")

        assert metadata.autov3 == "abcdef123456"

    @pytest.mark.parametrize(
        "hashes",
        [
            {},
            {"SHA256": "abc123"},
            {"SHA256": "abc123", "AutoV3": "abc"},
            {"SHA256": "abc123", "AutoV3": 123},
            {"SHA256": "abc123", "AutoV3": None},
        ],
    )
    @pytest.mark.parametrize("model_cls", [LoraMetadata, CheckpointMetadata, EmbeddingMetadata])
    def test_from_civitai_info_autov3_none_when_missing_or_invalid(self, model_cls, hashes):
        version_info = {
            "baseModel": "SDXL",
            "model": {"name": "Test", "description": "", "tags": []},
            "files": [{"name": "model.safetensors", "sizeKB": 1000, "hashes": hashes}],
        }
        file_info = {"name": "model.safetensors", "sizeKB": 1000, "hashes": {"SHA256": "abc123"}}

        metadata = model_cls.from_civitai_info(version_info, file_info, "/test/model.safetensors")

        assert metadata.autov3 is None

    def test_autov3_from_civitai_files_matches_sha256_case_insensitively(self):
        from py.utils.models import autov3_from_civitai_files

        civitai = {
            "files": [
                {"name": "a.safetensors", "hashes": {"SHA256": "111AAA"}},
                {"name": "b.safetensors", "hashes": {"SHA256": "222BBB", "AutoV3": "ABCDEF123456"}},
            ]
        }
        assert autov3_from_civitai_files(civitai, "222bbb") == "abcdef123456"
        assert autov3_from_civitai_files(civitai, "111aaa") is None
        assert autov3_from_civitai_files(civitai, "999999") is None
        assert autov3_from_civitai_files(None, "222bbb") is None
        assert autov3_from_civitai_files(civitai, "") is None

    def test_autov3_from_civitai_files_ignores_files_without_sha256(self):
        from py.utils.models import autov3_from_civitai_files

        civitai = {
            "files": [
                {"name": "a.safetensors", "hashes": {"AutoV3": "ABCDEF123456"}},
                {"name": "b.safetensors", "hashes": {"SHA256": "222BBB", "AutoV3": "123456ABCDEF"}},
            ]
        }
        assert autov3_from_civitai_files(civitai, "222bbb") == "123456abcdef"

    def test_autov3_from_civitai_files_rejects_empty_hash_placeholder(self):
        from py.utils.models import autov3_from_civitai_files

        civitai = {
            "files": [
                {"name": "b.safetensors", "hashes": {"SHA256": "222BBB", "AutoV3": "E3B0C44298FC1C149AFB..."}},
            ]
        }
        # The empty-string SHA256 placeholder must never be adopted as a value.
        assert autov3_from_civitai_files(civitai, "222bbb") is None

    def test_update_civitai_info_populates_autov3_from_matching_file(self):
        metadata = CheckpointMetadata(
            file_name="kreamania",
            model_name="Kreamania",
            file_path="/test/kreamania_variant5.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="111AABBF94DD9E59C05D842FCCF57BEC915B2A3C237F6B54F8D614E40858D717",
            base_model="FLUX.1 D",
            preview_url="",
            autov3="",
        )
        version_info = {
            "files": [
                {
                    "name": "kreamania_variant5.safetensors",
                    "hashes": {"SHA256": "111aabbf94dd9e59c05d842fccf57bec915b2a3c237f6b54f8d614e40858d717", "AutoV3": "8A582E901D7F"},
                }
            ]
        }

        metadata.update_civitai_info(version_info)

        assert metadata.autov3 == "8a582e901d7f"

    def test_update_civitai_info_prefers_civitai_over_header_value(self):
        metadata = BaseModelMetadata(
            file_name="model",
            model_name="Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
            autov3="e3b0c44298fc",  # stale header-extracted value
        )
        version_info = {
            "files": [
                {"name": "model.safetensors", "hashes": {"SHA256": "abc123", "AutoV3": "DEF456ABC789"}}
            ]
        }

        metadata.update_civitai_info(version_info)

        assert metadata.autov3 == "def456abc789"

    def test_update_civitai_info_keeps_autov3_when_no_match(self):
        metadata = BaseModelMetadata(
            file_name="model",
            model_name="Model",
            file_path="/test/model.safetensors",
            size=1000,
            modified=1234567890.0,
            sha256="abc123",
            base_model="SDXL",
            preview_url="",
            autov3="",
        )

        metadata.update_civitai_info({"files": [{"name": "other.safetensors", "hashes": {"SHA256": "zzz999", "AutoV3": "DEF456ABC789"}}]})

        assert metadata.autov3 == ""
