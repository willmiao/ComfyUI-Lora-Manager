"""Completion markers that gate the example-folder skip guard."""

from __future__ import annotations

from py.utils import example_images_download_manager as download_module
from py.utils.example_images_paths import (
    clear_example_completion_marker,
    has_completion_marker,
    mark_example_folder_complete,
)


def test_marker_requires_media_and_is_not_counted_as_a_file(tmp_path):
    model_dir = tmp_path / ("a" * 64)
    model_dir.mkdir()

    assert mark_example_folder_complete(str(model_dir)) is False
    assert has_completion_marker(str(model_dir)) is False

    (model_dir / "image_0.png").write_text("data", encoding="utf-8")
    assert mark_example_folder_complete(str(model_dir), media_count=1) is True
    assert has_completion_marker(str(model_dir)) is True
    assert download_module._model_directory_has_files(str(model_dir)) is True

    # A marker alone must never make the folder look populated again.
    (model_dir / "image_0.png").unlink()
    assert download_module._model_directory_has_files(str(model_dir)) is False

    clear_example_completion_marker(str(model_dir))
    assert has_completion_marker(str(model_dir)) is False


def test_folder_index_requires_a_marker(tmp_path):
    model_hash = "b" * 64
    model_dir = tmp_path / model_hash
    model_dir.mkdir()
    (model_dir / "image_0.png").write_text("data", encoding="utf-8")

    index = download_module._build_example_folder_index(str(tmp_path))
    assert index[model_hash] is False

    assert mark_example_folder_complete(str(model_dir), media_count=1) is True
    index = download_module._build_example_folder_index(str(tmp_path))
    assert index[model_hash] is True
