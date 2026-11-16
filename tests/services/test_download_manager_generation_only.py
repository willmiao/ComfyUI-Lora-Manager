"""Generation-Only download refusal.

CivitAI's per-version ``usageControl`` is the authoritative "may this version be
downloaded at all" signal. A Generation-Only version must be refused before any
download work starts; otherwise the 401/403 from the download endpoint is
reported as an early-access paywall, which is misleading.

The companion browser extension consumes the structured ``generation_only``
reason, so keep the value stable.
"""

from py.services.download_manager import (
    _generation_only_response,
    _is_generation_only_version,
)


def test_generation_usage_control_is_refused():
    assert _is_generation_only_version({"usageControl": "Generation"})


def test_usage_control_comparison_is_case_and_space_insensitive():
    assert _is_generation_only_version({"usageControl": "  generation  "})
    assert _is_generation_only_version({"usageControl": "InternalGeneration"})


def test_downloadable_or_missing_usage_control_is_allowed():
    assert not _is_generation_only_version({"usageControl": "Download"})
    assert not _is_generation_only_version({"usageControl": None})
    assert not _is_generation_only_version({})


def test_explicit_can_download_allowance_is_never_overridden():
    # Authenticated metadata may expose the viewer's entitlement (e.g. the
    # creator downloading their own Generation-Only model).
    assert not _is_generation_only_version(
        {"usageControl": "Generation", "canDownload": True}
    )


def test_civarchive_source_is_exempt():
    assert not _is_generation_only_version(
        {"usageControl": "Generation"}, source="civarchive"
    )


def test_structured_response_carries_a_stable_reason():
    response = _generation_only_response()
    assert response["success"] is False
    assert response["reason"] == "generation_only"
    assert "Generation-Only" in response["error"]


async def test_execute_original_download_refuses_before_download(monkeypatch):
    """The refusal happens right after the metadata fetch, before file selection."""
    from py.services import download_manager as download_manager_module

    class _StubProvider:
        async def get_model_version(self, model_id, version_id):
            return {
                "id": 1649921,
                "usageControl": "Generation",
                "files": [{"id": 1, "type": "Model", "primary": True}],
                "model": {"type": "LORA"},
            }

    async def _stub_default_provider():
        return _StubProvider()

    monkeypatch.setattr(
        download_manager_module,
        "get_default_metadata_provider",
        _stub_default_provider,
    )
    manager = object.__new__(download_manager_module.DownloadManager)

    result = await manager._execute_original_download(
        model_id=872135,
        model_version_id=None,
        save_dir=None,
        relative_path="",
        progress_callback=None,
        use_default_paths=False,
        source=None,
        file_params={},
    )

    assert result["success"] is False
    assert result["reason"] == "generation_only"
