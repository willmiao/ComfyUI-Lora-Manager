"""Tests for ``readme_processor.py`` — HF README processing for enrich_hf_metadata.

Import via ``importlib`` to avoid the ``folder_paths`` dependency in
``py.services.agent.__init__``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "py" / "services" / "agent" / "skills" / "enrich_hf_metadata" / "readme_processor.py"


@pytest.fixture(scope="session")
def R():
    """Load the ``readme_processor`` module once per session."""
    spec = importlib.util.spec_from_file_location("readme_processor", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ======================================================================
# extract_gallery_images
# ======================================================================


class TestExtractGalleryImages:
    def test_empty(self, R):
        assert R.extract_gallery_images("", "repo") == []
        assert R.extract_gallery_images("no frontmatter", "repo") == []

    def test_no_widget(self, R):
        readme = "---\ntags: [test]\n---\nbody"
        assert R.extract_gallery_images(readme, "repo") == []

    def test_widget_simple_text(self, R):
        """YAML ``text: 'plain'`` → extracted as-is."""
        readme = """---
widget:
- text: 'a cute cat'
  output:
    url: images/cat.png
---"""
        imgs = R.extract_gallery_images(readme, "user/repo")
        assert len(imgs) == 1
        assert imgs[0]["meta"]["prompt"] == "a cute cat"
        assert "images/cat.png" in imgs[0]["url"]

    def test_widget_unquoted_text(self, R):
        """YAML ``text: plain value`` without quotes."""
        readme = """---
widget:
- text: simple text
  output:
    url: img.png
---"""
        imgs = R.extract_gallery_images(readme, "user/repo")
        assert len(imgs) == 1
        assert imgs[0]["meta"]["prompt"] == "simple text"

    def test_widget_block_scalar(self, R):
        """YAML ``text: >-`` folded block scalar — extract actual content."""
        readme = """---
widget:
- text: >-
    Long toons, a close-up of a cartoon characters face is featured in a
    vibrant red backdrop.
  output:
    url: images/LT4.png
---"""
        imgs = R.extract_gallery_images(readme, "user/repo")
        assert len(imgs) == 1
        prompt = imgs[0]["meta"]["prompt"]
        assert "Long toons" in prompt
        assert "vibrant red backdrop" in prompt
        assert prompt != ">-"

    def test_widget_dash_prefix_output(self, R):
        """YAML ``- output:`` (dash prefix) — regression for widget parsing."""
        readme = """---
widget:
- output:
    url: images/test.png
  text: dash test
---"""
        imgs = R.extract_gallery_images(readme, "user/repo")
        assert len(imgs) == 1
        assert imgs[0]["meta"]["prompt"] == "dash test"
        assert "images/test.png" in imgs[0]["url"]

    def test_widget_mixed_entries(self, R):
        """Multiple widget entries with different text styles."""
        readme = """---
widget:
- text: >-
    First entry description.
  output:
    url: img1.png
- text: second entry
  output:
    url: img2.png
- text: 'third entry'
  output:
    url: img3.png
---"""
        imgs = R.extract_gallery_images(readme, "user/repo")
        assert len(imgs) == 3
        assert imgs[0]["meta"]["prompt"] == "First entry description."
        assert imgs[1]["meta"]["prompt"] == "second entry"
        assert imgs[2]["meta"]["prompt"] == "third entry"


# ======================================================================
# extract_simple_markdown_images
# ======================================================================


class TestExtractSimpleMarkdownImages:
    def test_empty(self, R):
        assert R.extract_simple_markdown_images("", "repo") == []

    def test_basic_markdown_image(self, R):
        """``![alt](./img.png)`` → absolute URL."""
        imgs = R.extract_simple_markdown_images("![test](./image_0.png)", "u/r")
        assert len(imgs) == 1
        assert "image_0.png" in imgs[0]["url"]
        assert imgs[0]["meta"]["prompt"] == "test"

    def test_absolute_url(self, R):
        """``![alt](https://...)`` → keep as-is."""
        imgs = R.extract_simple_markdown_images(
            "![img](https://example.com/img.png)", "u/r"
        )
        assert len(imgs) == 1
        assert imgs[0]["url"] == "https://example.com/img.png"

    def test_skips_code_fences(self, R):
        """Inside ``` blocks should be ignored."""
        text = """outside
```
![inside](./img.png)
```
outside again
![valid](./valid.png)"""
        imgs = R.extract_simple_markdown_images(text, "u/r")
        assert len(imgs) == 1
        assert "valid.png" in imgs[0]["url"]

    def test_deduplicates(self, R):
        text = "![a](./img.png)\n![b](./img.png)"
        imgs = R.extract_simple_markdown_images(text, "u/r")
        assert len(imgs) == 1  # deduplicated


# ======================================================================
# extract_html_img_tags
# ======================================================================


class TestExtractHtmlImgTags:
    def test_double_quoted_src(self, R):
        imgs = R.extract_html_img_tags('<img src="./img.png">', "u/r")
        assert len(imgs) == 1
        assert "img.png" in imgs[0]["url"]

    def test_single_quoted_src(self, R):
        imgs = R.extract_html_img_tags("<img src='./img.png'>", "u/r")
        assert len(imgs) == 1
        assert "img.png" in imgs[0]["url"]

    def test_absolute_url(self, R):
        imgs = R.extract_html_img_tags(
            '<img src="https://cdn.example.com/img.png">', "u/r"
        )
        assert len(imgs) == 1
        assert imgs[0]["url"] == "https://cdn.example.com/img.png"

    def test_deduplicates_across_formats(self, R):
        text = '<img src="./img.png">\n<img src=\'./img.png\'>'
        imgs = R.extract_html_img_tags(text, "u/r")
        assert len(imgs) == 1


# ======================================================================
# extract_gallery_table_images
# ======================================================================


class TestExtractGalleryTableImages:
    def test_gallery_table(self, R):
        text = """| Preview | Prompt |
|--------|--------|
| ![img](./a.png) | a cat |
| ![img](./b.png) | a dog |"""
        imgs = R.extract_gallery_table_images(text, "u/r")
        assert len(imgs) == 2
        assert imgs[0]["meta"]["prompt"] == "a cat"
        assert "a.png" in imgs[0]["url"]
        assert imgs[1]["meta"]["prompt"] == "a dog"

    def test_skips_non_gallery_table(self, R):
        text = """| Parameter | Value |
|----------|-------|
| Steps    | 4     |"""
        imgs = R.extract_gallery_table_images(text, "u/r")
        assert len(imgs) == 0


# ======================================================================
# clean_readme_for_llm  +  strip helpers
# ======================================================================


class TestCleanReadmeForLlm:
    def test_preserves_plain_code_block(self, R):
        """`` ``` `` without language tag → preserved (trigger words)."""
        text = """Before
```
pixel art sprite, game asset
```
After"""
        cleaned = R.clean_readme_for_llm(text)
        assert "pixel art sprite" in cleaned
        assert "game asset" in cleaned

    def test_strips_fenced_code_with_lang(self, R):
        """`` ```python `` → stripped."""
        text = "before\n```python\nimport torch\n```\nafter"
        cleaned = R.clean_readme_for_llm(text)
        assert "import torch" not in cleaned
        assert "before" in cleaned
        assert "after" in cleaned

    def test_preserves_markdown_image_url(self, R):
        """``![alt](url)`` → URL kept for LLM preview extraction."""
        text = "![sample](./preview.png)"
        cleaned = R.clean_readme_for_llm(text)
        assert "./preview.png" in cleaned

    def test_converts_html_img_tag_to_markdown_image(self, R):
        """``<img src="...">`` → ``![](src)`` preserving URL for LLM."""
        text = 'before\n<img src="logo.png">\nafter'
        cleaned = R.clean_readme_for_llm(text)
        assert "![](logo.png)" in cleaned
        assert "logo.png" in cleaned  # URL preserved for LLM extraction

    def test_widget_stripped_frontmatter_preserved(self, R):
        """Widget YAML stripped but ``base_model:`` kept."""
        text = """---
tags: [test]
widget:
- text: >-
    long description here
  output:
    url: img.png
base_model: black-forest-labs/FLUX.1-dev
instance_prompt: test
---"""
        cleaned = R.clean_readme_for_llm(text)
        assert "widget:" not in cleaned
        assert "black-forest-labs/FLUX.1-dev" in cleaned
        assert "instance_prompt: test" in cleaned

    def test_training_table_stripped(self, R):
        """Training-parameter table → stripped."""
        text = """before
| LR Scheduler | constant |
|--------------|---------|
| Optimizer    | AdamW   |
after"""
        cleaned = R.clean_readme_for_llm(text)
        assert "LR Scheduler" not in cleaned
        assert "Optimizer" not in cleaned
        assert "before" in cleaned
        assert "after" in cleaned

    def test_best_dimensions_table_kept(self, R):
        """Non-training table (Best Dimensions) → kept."""
        text = """## Best Dimensions
- 768 x 1024 (Best)
- 1024 x 1024 (Default)"""
        cleaned = R.clean_readme_for_llm(text)
        assert "768 x 1024" in cleaned

    def test_boilerplate_section_stripped(self, R):
        text = """stuff
## Download model
[link](url)
## Next section
content"""
        cleaned = R.clean_readme_for_llm(text)
        assert "Download model" not in cleaned
        assert "Next section" in cleaned
        assert "content" in cleaned

    def test_returns_empty_for_none(self, R):
        assert R.clean_readme_for_llm(None) == ""

    def test_returns_empty_for_empty(self, R):
        assert R.clean_readme_for_llm("") == ""


# ======================================================================
# _is_heading  /  _heading_level
# ======================================================================


class TestHeadingDetection:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("# Title", 1),
            ("## Sub", 2),
            ("### Subsub", 3),
            ("#### Subsubsub", 4),
            ("<h1>Title</h1>", 1),
            ("<h2>Sub</h2>", 2),
            ("<h3 class='x'>Sub</h3>", 3),
            ("<h4 id='y'>Sub</h4>", 4),
            ("not a heading", 0),
            ("###", 0),  # no text after ###
            ("</h2>", 0),  # closing tag, not a heading
            ("", 0),
        ],
    )
    def test_heading_level(self, R, line, expected):
        assert R._heading_level(line) == expected

    @pytest.mark.parametrize(
        "line,expected",
        [
            ("# Title", True),
            ("<h2>Sub</h2>", True),
            ("</h2>", False),  # closing tag
            ("not heading", False),
        ],
    )
    def test_is_heading(self, R, line, expected):
        assert R._is_heading(line) == expected


# ======================================================================
# extract_relevant_section
# ======================================================================


class TestExtractRelevantSection:
    def test_fallback_full_readme(self, R):
        """No match → full README returned."""
        readme = "# Title\n\nsome content"
        assert R.extract_relevant_section(readme, "nonexistent") == readme

    def test_empty_basename_returns_full(self, R):
        readme = "# Title"
        assert R.extract_relevant_section(readme, "") == readme

    def test_match_heading_includes_yaml(self, R):
        """Matching heading should still include YAML frontmatter."""
        readme = """---
base_model: foo
---
# My-Model-Title

content
## Subsection
more"""
        section = R.extract_relevant_section(readme, "My-Model")
        assert "base_model: foo" in section
        assert "content" in section
        assert "Subsection" in section

    def test_match_heading_includes_subheadings(self, R):
        """``# Title`` match includes all ``##`` children."""
        readme = """# Main Title

## Child A
content A
## Child B
content B
## Child C
content C"""
        section = R.extract_relevant_section(readme, "Main Title")
        assert "Child A" in section
        assert "Child B" in section
        assert "Child C" in section

    def test_match_download_link(self, R):
        """Download link containing basename → section extracted."""
        readme = """# Collection
## Model A
[Download](./model_a.safetensors)
## MyModel
[Download](./mymodel.safetensors)
content here
## Model B
other"""
        section = R.extract_relevant_section(readme, "mymodel")
        assert "content here" in section
        assert "Model A" not in section  # should not include sibling

    def test_heading_closing_tag_not_boundary(self, R):
        """``</h2>`` should NOT be treated as a section boundary."""
        readme = """# Title
<p>some text</p>
</h2>
## Real Section
content"""
        section = R.extract_relevant_section(readme, "Title")
        assert "Real Section" in section  # forward walk should not stop at </h2>
        assert "content" in section


# ======================================================================
# _extract_frontmatter
# ======================================================================


class TestExtractFrontmatter:
    def test_basic(self, R):
        assert R._extract_frontmatter("---\ntags: [a]\n---\nbody") == "\ntags: [a]\n"

    def test_no_frontmatter(self, R):
        assert R._extract_frontmatter("no dashes") == ""

    def test_empty_string(self, R):
        assert R._extract_frontmatter("") == ""


# ======================================================================
# _strip_widget_section
# ======================================================================


class TestStripWidgetSection:
    def test_strip_widget_keep_base_model(self, R):
        """Widget stripped but ``base_model:`` preserved."""
        text = """---
tags: [test]
widget:
- text: >-
    long text
  output:
    url: img.png
base_model: black-forest-labs/FLUX.1-dev
---"""
        result = R._strip_widget_section(text)
        assert "widget:" not in result
        assert "black-forest-labs/FLUX.1-dev" in result

    def test_no_widget_no_change(self, R):
        text = "---\ntags: [a]\n---"
        assert R._strip_widget_section(text) == text

    def test_widget_at_end_of_frontmatter(self, R):
        """Widget is the last YAML key before closing ---."""
        text = """---
base_model: a
widget:
- text: x
  output:
    url: y.png
---"""
        result = R._strip_widget_section(text)
        assert "widget:" not in result
        assert "base_model: a" in result


# ======================================================================
# _strip_fenced_code_blocks
# ======================================================================


class TestStripFencedCodeBlocks:
    def test_strips_with_language(self, R):
        text = "a\n```python\ncode\n```\nb"
        assert R._strip_fenced_code_blocks(text) == "a\nb"

    def test_keeps_plain_fence(self, R):
        """`` ``` `` without language → preserved."""
        text = "a\n```\ntrigger words\n```\nb"
        assert "trigger words" in R._strip_fenced_code_blocks(text)

    def test_pattern(self, R):
        text = "x\n```yaml\nkey: val\n```\ny"
        assert "key: val" not in R._strip_fenced_code_blocks(text)
