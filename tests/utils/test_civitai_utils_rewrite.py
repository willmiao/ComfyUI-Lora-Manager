"""Tests for CivitAI URL utilities."""

import pytest

from py.utils.civitai_utils import rewrite_preview_url


class TestRewritePreviewUrl:
    """Test cases for rewrite_preview_url function."""

    def test_handles_none_input(self):
        """Should return (None, False) for None input."""
        result, was_rewritten = rewrite_preview_url(None)
        assert result is None
        assert was_rewritten is False

    def test_handles_empty_string(self):
        """Should return (empty_string, False) for empty input."""
        result, was_rewritten = rewrite_preview_url("")
        assert result == ""
        assert was_rewritten is False

    def test_handles_invalid_url(self):
        """Should return original URL and False for invalid URLs."""
        invalid_url = "not-a-valid-url"
        result, was_rewritten = rewrite_preview_url(invalid_url)
        assert result == invalid_url
        assert was_rewritten is False

    def test_handles_url_without_scheme(self):
        """Should return original URL and False for URLs without scheme."""
        url = "image.civitai.com/something"
        result, was_rewritten = rewrite_preview_url(url)
        assert result == url
        assert was_rewritten is False

    def test_returns_false_for_non_civitai_domains(self):
        """Should not rewrite URLs from other domains."""
        url = "https://example.com/image.jpg"
        result, was_rewritten = rewrite_preview_url(url)
        assert result == url
        assert was_rewritten is False

    def test_returns_false_for_main_civitai_domain(self):
        """Should not rewrite URLs from main civitai.com domain."""
        url = "https://civitai.com/images/123"
        result, was_rewritten = rewrite_preview_url(url)
        assert result == url
        assert was_rewritten is False

    def test_rewrites_image_civitai_com_urls(self):
        """Should rewrite URLs from image.civitai.com."""
        url = "https://image.civitai.com/checkpoints/original=true"
        result, was_rewritten = rewrite_preview_url(url, "image")
        assert (
            result == "https://image.civitai.com/checkpoints/width=450,optimized=true"
        )
        assert was_rewritten is True

    def test_rewrites_subdomain_civitai_urls(self):
        """Should rewrite URLs from CivitAI CDN subdomains like image-b2.civitai.com."""
        url = "https://image-b2.civitai.com/file/civitai-media-cache/original=true/sample.png"
        result, was_rewritten = rewrite_preview_url(url, "image")
        assert (
            result
            == "https://image-b2.civitai.com/file/civitai-media-cache/width=450,optimized=true/sample.png"
        )
        assert was_rewritten is True

    def test_rewrites_multiple_subdomains(self):
        """Should rewrite URLs from various CivitAI subdomains."""
        test_cases = [
            "https://image-b3.civitai.com/original=true/test.jpg",
            "https://cdn.civitai.com/original=true/test.png",
        ]
        for url in test_cases:
            result, was_rewritten = rewrite_preview_url(url, "image")
            assert was_rewritten is True
            assert "width=450,optimized=true" in result

    def test_handles_urls_with_explicit_port(self):
        """Should correctly handle URLs with explicit port numbers."""
        url = "https://image.civitai.com:443/checkpoints/original=true"
        result, was_rewritten = rewrite_preview_url(url, "image")
        assert was_rewritten is True
        assert "width=450,optimized=true" in result
        # Port is preserved in the URL (this is acceptable behavior)
        assert ":443" in result

    def test_rewrites_video_urls_with_transcode(self):
        """Should rewrite video URLs with transcode parameter."""
        url = "https://image.civitai.com/videos/original=true/sample.mp4"
        result, was_rewritten = rewrite_preview_url(url, "video")
        assert (
            result
            == "https://image.civitai.com/videos/transcode=true,width=450,optimized=true/sample.mp4"
        )
        assert was_rewritten is True

    def test_video_rewrite_uses_case_insensitive_type(self):
        """Should handle video type case-insensitively."""
        url = "https://image.civitai.com/original=true/test.mp4"
        result1, was1 = rewrite_preview_url(url, "VIDEO")
        result2, was2 = rewrite_preview_url(url, "Video")
        assert was1 is True
        assert was2 is True
        assert "transcode=true" in result1
        assert "transcode=true" in result2

    def test_returns_original_when_no_original_true_in_path(self):
        """Should not rewrite URLs that don't contain /original=true."""
        url = "https://image.civitai.com/checkpoints/optimized=true"
        result, was_rewritten = rewrite_preview_url(url)
        assert result == url
        assert was_rewritten is False

    def test_preserves_path_structure_after_rewrite(self):
        """Should maintain path structure after rewriting."""
        url = "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/original=true/12345.png"
        result, was_rewritten = rewrite_preview_url(url, "image")
        assert was_rewritten is True
        assert result.startswith(
            "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/abc123/"
        )
        assert result.endswith("/12345.png")

    def test_defaults_to_image_mode_when_media_type_is_none(self):
        """Should use image optimization when media_type is None."""
        url = "https://image.civitai.com/original=true/test.png"
        result, was_rewritten = rewrite_preview_url(url, None)
        assert was_rewritten is True
        assert "transcode=true" not in result
        assert "width=450,optimized=true" in result

    def test_case_insensitive_hostname_matching(self):
        """Should handle case-insensitive hostname matching."""
        test_cases = [
            "https://IMAGE.CIVITAI.COM/original=true/test.png",
            "https://Image.Civitai.Com/original=true/test.png",
            "https://image-b2.CIVITAI.com/original=true/test.png",
        ]
        for url in test_cases:
            result, was_rewritten = rewrite_preview_url(url, "image")
            assert was_rewritten is True, f"Failed for URL: {url}"
