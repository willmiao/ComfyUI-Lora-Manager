"""HF README processing for the ``enrich_hf_metadata`` skill.

Provides README cleaning for LLM injection, gallery/image extraction from
multiple formats (YAML widget, markdown, HTML ``<img>``, gallery tables),
and section-based README trimming for collection repos.
"""

from __future__ import annotations

import html as html_module
import re
from typing import List, Tuple


_REPO_URL_PATTERN = re.compile(r"https?://huggingface\.co/([^/]+/[^/]+)")


def extract_simple_markdown_images(
    markdown_text: str,
    repo: str,
    existing_urls: set | None = None,
    default_width: int = 512,
    default_height: int = 512,
) -> list[dict]:
    """Extract standalone markdown images from the README body.

    Matches ``![alt](url)`` on lines that are NOT part of a markdown table
    and NOT inside fenced code blocks.  These are common in DreamBooth
    training dumps where the user uploads example images with simple
    ``![img_0](./image_0.png)`` syntax.

    Returns a list of dicts in the same ``civitai.images`` format as
    :func:`extract_gallery_images`.
    """
    if not markdown_text or not repo:
        return []

    base_url = f"https://huggingface.co/{repo}/resolve/main"
    images: list[dict] = []
    seen_urls: set = set(existing_urls) if existing_urls else set()

    # Collect lines that are NOT inside fenced code blocks
    lines = markdown_text.split("\n")
    in_code_block = False
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            i += 1
            continue
        # Skip table rows
        if "|" in line and i + 1 < n and re.match(r"^\|[\s:-]+\|", lines[i + 1]):
            i += 1
            continue

        m = re.match(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if m:
            raw_path = m.group(2).strip()
            if raw_path.startswith("http"):
                url = raw_path
            else:
                clean = raw_path.lstrip("./").lstrip("/")
                url = f"{base_url}/{clean}"
            if url not in seen_urls:
                seen_urls.add(url)
                images.append({
                    "url": url,
                    "type": "image",
                    "nsfwLevel": 0,
                    "width": default_width,
                    "height": default_height,
                    "meta": {"prompt": m.group(1), "negativePrompt": ""},
                    "hasMeta": bool(m.group(1)),
                    "hasPositivePrompt": bool(m.group(1)),
                })
        i += 1

    return images


def extract_html_img_tags(
    markdown_text: str,
    repo: str,
    existing_urls: set | None = None,
    default_width: int = 512,
    default_height: int = 512,
) -> list[dict]:
    """Extract image URLs from HTML ``<img src=\"...\">`` tags in the README.

    Many HF collection repos (e.g. ``deadman44/Z-Image_LoRA``) use raw HTML
    ``<img>`` tags exclusively for their sample images, with no markdown
    ``![]()`` equivalents.  This function finds those tags and constructs
    resolvable HF URLs.

    Returns a list of dicts in the ``civitai.images`` format.
    """
    if not markdown_text or not repo:
        return []

    base_url = f"https://huggingface.co/{repo}/resolve/main"
    images: list[dict] = []
    seen_urls: set = set(existing_urls) if existing_urls else set()

    for m in re.finditer(
        r'<img\s[^>]*src=\"([^\"]+)\"',
        markdown_text,
        re.IGNORECASE,
    ):
        raw_path = m.group(1).strip()
        if not raw_path:
            continue

        if raw_path.startswith("http"):
            url = raw_path
        else:
            clean = raw_path.lstrip("./").lstrip("/")
            url = f"{base_url}/{clean}"

        if url and url not in seen_urls:
            seen_urls.add(url)
            images.append({
                "url": url,
                "type": "image",
                "nsfwLevel": 0,
                "width": default_width,
                "height": default_height,
                "meta": {"prompt": "", "negativePrompt": ""},
                "hasMeta": False,
                "hasPositivePrompt": False,
            })

    # Also try single-quoted src attributes
    for m in re.finditer(
        r"<img\s[^>]*src='([^']+)'",
        markdown_text,
        re.IGNORECASE,
    ):
        raw_path = m.group(1).strip()
        if not raw_path:
            continue
        if raw_path.startswith("http"):
            url = raw_path
        else:
            clean = raw_path.lstrip("./").lstrip("/")
            url = f"{base_url}/{clean}"
        if url and url not in seen_urls:
            seen_urls.add(url)
            images.append({
                "url": url,
                "type": "image",
                "nsfwLevel": 0,
                "width": default_width,
                "height": default_height,
                "meta": {"prompt": "", "negativePrompt": ""},
                "hasMeta": False,
                "hasPositivePrompt": False,
            })

    return images


def extract_repo_from_hf_url(hf_url: str) -> str:
    """Extract ``user/repo`` from a HuggingFace URL."""
    m = _REPO_URL_PATTERN.match(hf_url)
    return m.group(1) if m else ""


def extract_gallery_images(
    markdown_text: str,
    repo: str,
    default_width: int = 512,
    default_height: int = 512,
) -> List[dict]:
    """Extract widget/gallery images from the YAML frontmatter of a HF README.

    Args:
        markdown_text: Raw README content.
        repo: HF repo identifier (``user/repo``).
        default_width: Fallback width when the README provides no dimension.
        default_height: Fallback height when the README provides no dimension.

    Returns a list of dicts compatible with the ``civitai.images`` metadata
    format, each containing ``url`` (absolute HF URL), ``meta.prompt``,
    ``width``, ``height``, and ``type``.  Returns an empty list when no
    widget entries are found or when *repo* is empty.
    """
    if not markdown_text or not repo:
        return []

    frontmatter = _extract_frontmatter(markdown_text)
    if not frontmatter:
        return []

    images: List[dict] = []
    base_url = f"https://huggingface.co/{repo}/resolve/main"
    w = default_width or 512
    h = default_height or 512

    # Find the `widget:` section
    widget_match = re.search(r"^widget:\s*$", frontmatter, re.MULTILINE)
    if not widget_match:
        return images

    # Split entries by YAML list marker `\n- `.  Each entry is one widget list
    # item with `output:` and optionally `text:` sub-keys.
    entries_raw = frontmatter[widget_match.end():]
    entries = re.split(r"\n- ", entries_raw) if "\n- " in entries_raw else [entries_raw]

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Extract output.url — handle both `output:` and `- output:` (dash prefix)
        url = ""
        url_match = re.search(
            r"^-?\s*output:\s*\n\s+url:\s*(.+?)\s*$", entry, re.MULTILINE
        )
        if url_match:
            raw_path = url_match.group(1).strip().strip("'\"")
            if raw_path and not raw_path.startswith("http"):
                url = f"{base_url}/{raw_path.lstrip('/')}"
            elif raw_path.startswith("http"):
                url = raw_path

        # Extract text (prompt) — from YAML `text:` sub-key
        text = ""
        text_match = re.search(
            r"^-?\s*text:\s*(.+?)\s*$", entry, re.MULTILINE
        )
        if text_match:
            raw_text = text_match.group(1).strip().strip("'\"")
            if raw_text and raw_text != "-":
                # Handle YAML block scalar markers (>-, >, |, |-) where the
                # actual text lives on subsequent indented lines.
                if raw_text in (">", ">-", "|", "|-"):
                    text_lines: list[str] = []
                    in_block = False
                    for line in entry.split("\n"):
                        stripped = line.strip()
                        if not in_block:
                            if stripped.endswith(raw_text):
                                in_block = True
                            continue
                        # Block content ends at a line with less indentation
                        # or a YAML key at the start of a line.
                        if not stripped or re.match(r"^\s*\w+:", line):
                            break
                        if stripped:
                            text_lines.append(stripped)
                    text = " ".join(text_lines)
                else:
                    text = raw_text

        if url:
            image: dict = {
                "url": url,
                "type": "image",
                "nsfwLevel": 0,
                "width": w,
                "height": h,
                "meta": {"prompt": text, "negativePrompt": ""},
                "hasMeta": bool(text),
                "hasPositivePrompt": bool(text),
            }
            images.append(image)

    return images


def extract_gallery_table_images(
    markdown_text: str,
    repo: str,
    existing_urls: set | None = None,
    default_width: int = 512,
    default_height: int = 512,
) -> list[dict]:
    """Extract images from ``| Preview | Prompt |`` markdown gallery tables.

    Many HF READMEs include a sample-gallery table in the body (outside
    the YAML frontmatter) that shows generation examples with their
    prompts.  This function parses those tables and merges results with
    the widget-sourced images from :func:`extract_gallery_images`.

    Returns a list of dicts in the same ``civitai.images`` format as
    :func:`extract_gallery_images`.  Already-seen URLs (from *existing_urls*)
    are skipped.
    """
    if not markdown_text or not repo:
        return []

    base_url = f"https://huggingface.co/{repo}/resolve/main"
    images: list[dict] = []
    seen_urls: set = set(existing_urls) if existing_urls else set()
    lines = markdown_text.split("\n")
    n = len(lines)
    i = 0

    while i < n:
        line = lines[i]
        if "|" not in line or i + 1 >= n:
            i += 1
            continue

        # Check for table separator row
        if not re.match(r"^\|[\s:-]+\|", lines[i + 1]):
            i += 1
            continue

        header_lower = line.strip().lower()
        first_cell = header_lower.strip("|").split("|")[0].strip() if "|" in header_lower else ""
        is_gallery = any(kw in first_cell for kw in ("preview", "sample", "gallery", "image", "thumbnail"))
        if not is_gallery:
            i += 1
            continue

        # Skip header + separator
        i += 2
        while i < n and "|" in lines[i]:
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            if len(cells) >= 2:
                first = cells[0]
                prompt = cells[1]

                url_match = re.search(r"!\[([^\]]*)\]\(([^)]+)\)", first)
                if url_match:
                    raw_path = url_match.group(2)
                    if raw_path.startswith("http"):
                        url = raw_path
                    else:
                        # Normalise: remove leading / and ./ prefixes
                        clean = raw_path.lstrip("./").lstrip("/")
                        url = f"{base_url}/{clean}"

                    if url not in seen_urls:
                        seen_urls.add(url)
                        images.append({
                            "url": url,
                            "type": "image",
                            "nsfwLevel": 0,
                            "width": default_width,
                            "height": default_height,
                            "meta": {"prompt": prompt, "negativePrompt": ""},
                            "hasMeta": bool(prompt),
                            "hasPositivePrompt": bool(prompt),
                        })
            i += 1
        continue

    return images


def _extract_frontmatter(text: str) -> str:
    """Return the YAML frontmatter content (without the ``---`` delimiters).

    Returns empty string when no frontmatter is found.
    """
    if text.startswith("---"):
        idx = text.find("---", 3)
        if idx != -1:
            return text[3:idx]
    return ""


def convert_readme_to_html(markdown_text: str | None) -> str:
    """Convert HF README markdown to sanitised HTML."""
    if not markdown_text:
        return ""

    text = markdown_text
    text = _strip_frontmatter(text)
    text = _strip_gallery(text)
    text = _strip_badge_images(text)
    text = _strip_html_comments(text)
    html = _md_to_html(text)
    return html.strip()


# ---------------------------------------------------------------------------
# README cleaning for LLM prompt injection
# ---------------------------------------------------------------------------

#: Section headers that signal boilerplate content with zero metadata value.
_BOILERPLATE_HEADERS: tuple[str, ...] = (
    "download model",
    "license",
    "citation",
    "links",
    "disclaimer",
    "architecture notes",
    "training details",
    "dataset",
    "provenance",
)

#: Table header keywords that identify training-parameter tables.
_TRAINING_PARAM_KEYWORDS: tuple[str, ...] = (
    "lr scheduler",
    "optimizer",
    "network dim",
    "network alpha",
    "noise offset",
    "multires noise",
    "repeat",
    "epoch",
    "batch size",
    "gradient accumulation",
    "learning rate",
    "rslora",
    "dtype",
)

#: Maximum chars before a single-line comma list is considered massive.
_MASSIVE_LIST_LINE_MIN_LEN = 150
#: Minimum consecutive enumeration lines to trigger massive-list stripping.
_MASSIVE_LIST_THRESHOLD = 8


def clean_readme_for_llm(markdown_text: str | None, max_length: int = 6000) -> str:
    """Clean a HF README for injection into an LLM metadata-extraction prompt.

    Removes content that carries no signal for inferring base model,
    trigger words, short description, tags, or a preview image URL:

    * ``widget:`` YAML block (example prompts + output URLs)
    * ``<Gallery />`` tags and wrappers
    * Fenced code blocks (Python / bash / bibtex / yaml)
    * Standalone ``![...](...)`` image lines and ``<img>`` tags
    * Training-parameter tables
    * Boilerplate sections (Download / License / Citation / …)
    * Massive enumeration lists (e.g. 3000+ celebrity names)

    The post-processor still receives the **full** raw README via
    ``readme_content_full``, so nothing is lost for HTML conversion or
    gallery-image extraction.

    Args:
        markdown_text: Raw README.md content from HuggingFace.
        max_length: Hard ceiling on output length (default 6 000 chars).

    Returns:
        Cleaned markdown, truncated to *max_length*.
    """
    if not markdown_text:
        return ""

    text = markdown_text

    # Order matters — broader strips first, then finer ones.
    text = _strip_gallery(text)
    text = _strip_widget_section(text)
    text = _strip_fenced_code_blocks(text)
    text = _strip_standalone_images(text)
    text = _strip_training_tables(text)
    text = _strip_boilerplate_sections(text)
    text = _strip_massive_lists(text)
    text = _strip_badge_images(text)
    text = _strip_html_comments(text)
    text = _compress_blank_lines(text)

    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()


def _strip_fenced_code_blocks(text: str) -> str:
    """Strip fenced code blocks that have an explicit programming-language tag.

    Blocks without a language tag (just `` ``` ``) are preserved — they
    often contain trigger words, example prompts, or config snippets
    rather than actual runnable code.
    """
    # Match opening ``` immediately followed by a word character (the language
    # tag), then any content, then closing ```.  Plain ``` at the start of a
    # line is left intact.  A leading \n is optional (handles blocks at the
    # start of the text).
    return re.sub(
        r"(?:\n|^)```[a-zA-Z_][a-zA-Z0-9_]*\s*\n.*?\n```",
        "",
        text,
        flags=re.DOTALL,
    )


def _strip_standalone_images(text: str) -> str:
    """Strip/compress image embeds for LLM-prompt injection.

    Markdown images (``![alt](url)``) are **kept intact** so the LLM can
    extract a ``preview_url`` from them.  Only the alt text is needed for
    content signal; the URL is needed for image extraction.

    HTML ``<img>`` tags on their own line are **converted to markdown
    image syntax** ``![alt](src)`` so both the alt text and the image URL
    are preserved in a format the LLM can easily extract.  Previously the
    URL was stripped entirely, making it impossible for the LLM to return
    a ``preview_url`` for repos that use HTML ``<img>`` tags exclusively.
    """
    def _img_to_md(match: re.Match) -> str:
        """Convert an ``<img>`` tag to markdown image syntax ``![alt](src)``."""
        tag = match.group(0)
        src_m = re.search(r'src="([^"]+)"', tag) or re.search(r"src='([^']+)'", tag)
        if not src_m:
            return ""
        src = src_m.group(1)
        alt_m = re.search(r'alt="([^"]*)"', tag) or re.search(r"alt='([^']*)'", tag)
        alt = alt_m.group(1) if alt_m else ""
        return f"![{alt}]({src})"

    text = re.sub(
        r'^\s*<img\s[^>]+/?>(?:</img>)?\s*$',
        _img_to_md,
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    return text


def _strip_training_tables(text: str) -> str:
    """Strip markdown tables whose header row mentions training parameters.

    Checks the header row (first line of a detected table) against
    ``_TRAINING_PARAM_KEYWORDS``.  Non-training tables (e.g. "Best
    Dimensions") are preserved.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if "|" in line and i + 1 < n and re.match(r"^\|[\s:-]+\|", lines[i + 1]):
            table_lines = [line]
            i += 1
            while i < n and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1

            # Check header + first data row for training keywords
            header_and_first = (line + "\n" + (table_lines[2] if len(table_lines) > 2 else "")).lower()
            if any(kw in header_and_first for kw in _TRAINING_PARAM_KEYWORDS):
                continue
            out.extend(table_lines)
        else:
            out.append(line)
            i += 1

    return "\n".join(out)


def _strip_boilerplate_sections(text: str) -> str:
    """Strip sections whose headings match known boilerplate patterns.

    When a heading (``## Download model``, ``## License``, etc.) is
    detected, the heading and all content until the next heading of
    equal-or-higher level is removed.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    skip_until_level: int | None = None

    while i < n:
        line = lines[i]
        h_match = re.match(r"^(#{1,4})\s+(.+?)\s*#*$", line)
        if h_match:
            level = len(h_match.group(1))
            title = h_match.group(2).strip().lower()

            is_boilerplate = any(
                title == kw or title.startswith(kw + " ") or title.startswith(kw + ":")
                for kw in _BOILERPLATE_HEADERS
            )

            if is_boilerplate:
                skip_until_level = level
                i += 1
                continue

            if skip_until_level is not None and level <= skip_until_level:
                skip_until_level = None

        if skip_until_level is None:
            out.append(line)
        i += 1

    return "\n".join(out)


def _strip_massive_lists(text: str) -> str:
    """Strip blocks of 8+ consecutive enumeration-style lines.

    Targets long comma-separated name lists (e.g. the 3000+ celebrity
    names in some Z-Image READMEs) and dense bullet enumerations.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        stripped = lines[i].strip()

        # A "list-like" line ends with comma or is a bullet with commas
        is_list_like = bool(stripped) and (
            stripped.endswith(",")
            or len(stripped) >= _MASSIVE_LIST_LINE_MIN_LEN
            or (bool(re.match(r"^[-*+]\s", stripped)) and "," in stripped)
        )

        if is_list_like:
            count = 1
            j = i + 1
            while j < n:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if s.endswith(",") or (bool(re.match(r"^[-*+]\s", s)) and "," in s):
                    count += 1
                    j += 1
                else:
                    break

            if count >= _MASSIVE_LIST_THRESHOLD:
                i = j
                continue

        out.append(lines[i])
        i += 1

    return "\n".join(out)


def extract_relevant_section(
    readme_content: str,
    model_basename: str,
    *,
    context_lines: int = 30,
) -> str:
    """Find the section of a HuggingFace README relevant to a specific model file.

    Many HF repos bundle multiple model files (LoRA collections) in a single
    repo.  This function trims the README to only the portion that references
    the given *model_basename* (e.g. ``lora_zimage_myjs_turbo_beta01``),
    dramatically reducing prompt length and focusing the LLM on the correct
    metadata.

    Matching strategies, tried in order:

    1. **Download link** — a markdown or HTML link whose URL contains the
       basename.  Returns the surrounding block (previous heading → next
       heading).
    2. **Anchor ID** — an ``<a id="...">`` whose ``id`` matches a token from
       the basename (split on ``_``/``-``).
    3. **Section heading** — an ``<h1>``-``<h4>`` or markdown heading whose
       text overlaps with tokens from the basename.
    4. **Fallback** — the full README unchanged.

    Args:
        readme_content: Raw README.md content.
        model_basename: Model file basename *without* extension (e.g.
            ``lora_zimage_myjs_turbo_beta01``).
        context_lines: Number of lines of context before/after a matched
            download link to include (default 30).

    Returns:
        Trimmed README text, or the original when no matching section is
        found.
    """
    if not readme_content or not model_basename:
        return readme_content or ""

    lines = readme_content.split("\n")
    n = len(lines)
    basename_lower = model_basename.lower()
    # Tokens from the basename split on common separators.
    # Exclude tokens of length ≤ 3 — 2-3 char tokens (e.g. "cry", "myjs")
    # are too short to discriminate between different models in collection repos.
    tokens = {t for t in re.split(r"[_\-.\s]+", basename_lower) if len(t) > 3}

    # ------------------------------------------------------------------
    # Strategy 1: Find a download link containing the basename
    # ------------------------------------------------------------------
    for idx, line in enumerate(lines):
        # Match markdown links: [text](url) and HTML links: <a href="url">
        # whose URL contains the basename.
        if basename_lower in line.lower() and _looks_like_download_link(line):
            return _extract_section(lines, idx, context_lines)

    # ------------------------------------------------------------------
    # Strategy 2: Find an anchor ID matching a token
    # ------------------------------------------------------------------
    for idx, line in enumerate(lines):
        m = re.search(r'<a\s+id="([^"]+)"', line, re.IGNORECASE)
        if m:
            aid = m.group(1).lower()
            if any(token in aid for token in tokens):
                section = _extract_section(lines, idx, context_lines)
                # Verify the extracted section actually mentions the model —
                # short anchor IDs can coincidentally match tokens from
                # unrelated models (e.g. "myjs" matching a different LoRA).
                if basename_lower in section.lower():
                    return section
                # False positive — continue searching

    # ------------------------------------------------------------------
    # Strategy 3: Find an HTML or markdown heading with overlapping tokens
    # ------------------------------------------------------------------
    for idx, line in enumerate(lines):
        # HTML heading: <h1...>, <h2...>, <h3...>, <h4...>
        hm = re.search(r'<h[1-4][^>]*>(.+?)</h[1-4]>', line, re.IGNORECASE)
        heading_text = ""
        if hm:
            heading_text = hm.group(1)
        else:
            # Markdown heading: ## text
            mm = re.match(r"^#{1,4}\s+(.+?)\s*#*$", line)
            if mm:
                heading_text = mm.group(1)
        if heading_text:
            # Skip TOC-style entries where the heading text is a markdown
            # link or bullet list item (e.g. "### - [model_name](url)").
            # These are table-of-contents entries, not real section headers.
            stripped = heading_text.strip()
            if stripped.startswith("- [") or re.match(r"^\[.+?\]\(.+?\)", stripped):
                continue

            heading_lower = heading_text.lower()
            # Require at least 2 token overlaps, or the full basename as a
            # substring of the heading.  A single 4-5 char token match is
            # too weak — e.g. "devil" matching "dante_devil_may_cry" when
            # the actual model is "vergil_devil_may_cry", or "image" matching
            # a table-of-contents heading.
            matching = [t for t in tokens if t in heading_lower]
            if len(matching) >= 2 or basename_lower in heading_lower:
                section = _extract_section(lines, idx, context_lines)
                # Verify the section contains the model name — headings in
                # TOC areas can match tokens but produce a tiny irrelevant
                # section (e.g. "### - [z_image_turbo](url)" matched by
                # tokens "lora" and "turbo").
                if basename_lower in section.lower() or len(section) > max(500, context_lines * 20):
                    return section

    # ------------------------------------------------------------------
    # Fallback: return FULL readme
    # ------------------------------------------------------------------
    return readme_content


def _looks_like_download_link(line: str) -> bool:
    """Heuristic: does *line* look like it contains a model-file download link?"""
    # Markdown: [text](url)
    if re.search(r'\[([^\]]*)\]\(([^)]*\.safetensors[^)]*)\)', line):
        return True
    # Markdown: [text](url) containing "download" or "resolve"
    if re.search(r'\[([^\]]*)\]\(([^)]*/(resolve|download)/[^)]*)\)', line):
        return True
    # HTML <a href="...safetensors">
    if re.search(r'<a\s[^>]*href="[^"]*\.safetensors', line, re.IGNORECASE):
        return True
    return False


def _heading_level(line: str) -> int:
    """Return the heading level of *line* (1-4), or 0 if not a heading."""
    stripped = line.strip()
    m = re.match(r"^(#{1,4})\s", stripped)
    if m:
        return len(m.group(1))
    m = re.match(r"^<h([1-4])(?:\s|>)", stripped, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def _extract_section(
    lines: list[str], match_idx: int, context_lines: int,
) -> str:
    """Return a window of *lines* around *match_idx* bounded by headings.

    When *match_idx* is itself a heading line, the section starts *at*
    that heading (no backward walk), avoiding pulling in content from
    earlier sibling sections.  The forward walk stops at a heading of
    **equal or higher** level (e.g. a ``# Title`` match includes all its
    ``## Children``).

    When *match_idx* is **not** a heading (e.g. a download link matched
    inside a sub-section like ``# Download``), the forward walk uses a
    generous line-count-based window instead of stopping at the very next
    heading.  This prevents same-level sub-headings (e.g. ``# Download``,
    ``# Trigger``, ``# Sample prompt`` within a single model section)
    from prematurely truncating the window before sample images.

    Always includes the YAML frontmatter if the original lines contain one,
    because it carries critical metadata (``base_model``, ``tags``,
    ``instance_prompt``) that the LLM needs regardless of which section
    matches.
    """
    n = len(lines)

    # Determine start — if match is a heading, start right there
    if _is_heading(lines[match_idx]):
        start = match_idx
        match_level = _heading_level(lines[match_idx])
    else:
        match_level = 0
        start = max(0, match_idx - context_lines)
        for i in range(match_idx - 1, max(-1, match_idx - context_lines * 3), -1):
            if i < 0:
                start = 0
                break
            if _is_heading(lines[i]):
                start = i
                break

    # Walk forward.
    end = n
    if match_level == 0:
        # Non-heading match (e.g. a download link).  Use a line-based
        # window so that same-level sub-headings (# Download, # Trigger,
        # # Sample prompt within a single model section) don't truncate
        # the window.  Stop at the next <a id="..."> anchor (which
        # typically starts a new model section in collection repos), or
        # fall back to a generous line limit.
        forward_limit = min(n, match_idx + max(context_lines * 3, 250))
        for i in range(match_idx + 1, forward_limit):
            if re.search(r'<a\s+id="', lines[i], re.IGNORECASE):
                end = i
                break
        else:
            end = forward_limit
    else:
        # Heading match — stop at the next heading of equal or higher
        # level, so that a # Title encompasses all its ## Children.
        walk_limit = min(n, match_idx + max(context_lines * 3, 120))
        for i in range(match_idx + 1, walk_limit):
            hl = _heading_level(lines[i])
            if hl > 0 and hl <= match_level:
                end = i
                break

    # If YAML frontmatter exists before the matched section, prepend it.
    if start > 0 and len(lines) > 1 and lines[0].strip() == "---":
        for i in range(1, min(start, len(lines))):
            if lines[i].strip() == "---":
                yaml_section = "\n".join(lines[:i+1])
                return yaml_section + "\n" + "\n".join(lines[start:end])

    return "\n".join(lines[start:end])


def _is_heading(line: str) -> bool:
    """Return True if *line* is a markdown or HTML heading (not a closing tag)."""
    stripped = line.strip()
    if re.match(r"^#{1,4}\s", stripped):
        return True
    if re.match(r"^<h[1-4](?:\s|>)", stripped, re.IGNORECASE):
        return True
    return False


def _compress_blank_lines(text: str) -> str:
    """Collapse runs of 3+ blank lines down to 2."""
    return re.sub(r"\n{3,}", "\n\n", text)


# ---------------------------------------------------------------------------
# Pre-processing: strip unwanted sections (HTML conversion helpers)
# ---------------------------------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        idx = text.find("---", 3)
        if idx != -1:
            return text[idx + 3 :]
    return text


def _strip_gallery(text: str) -> str:
    text = re.sub(
        r"<Gallery\b[^>]*/>|<Gallery\b[^>]*>.*?</Gallery>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r'<div\s+[^>]*flex[^>]*>.*?(?:<Gallery\b|</?\w+\s+[^>]*gallery).*?</div>',
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return text


def _strip_widget_section(text: str) -> str:
    """Strip the ``widget:`` YAML block from the README frontmatter.

    The widget section contains verbose example prompts (``text: >-`` entries)
    that are useful for post-processor gallery image extraction but carry
    no signal for LLM metadata extraction.  Stripping them dramatically
    reduces prompt size (e.g. 2800+ chars → ~100 chars) and lets the LLM
    focus on the actual YAML metadata fields (``base_model``, ``tags``,
    ``instance_prompt``, etc.).
    """
    # Match widget: through the end of the frontmatter (the closing ---)
    # or until the next YAML top-level key.
    return re.sub(
        r"\nwidget:.*?(?=\n\w+:|\n---)",
        "",
        text,
        flags=re.DOTALL,
    )


def _strip_badge_images(text: str) -> str:
    badge_keywords = (
        "badge", "shield", "logo", "icon", "download", "license",
        "python", "version", "status", "build", "test", "coverage",
        "docker", "pypi", "npm", "github", "hugging face", "discord",
        "twitter", "colab", "gradio", "space",
    )

    def _should_remove(m: re.Match) -> str:
        alt = (m.group(1) or "").lower()
        for kw in badge_keywords:
            if kw in alt:
                return ""
        return m.group(0)

    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", _should_remove, text)
    return text


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# Markdown → HTML rendering
# ---------------------------------------------------------------------------


def _md_to_html(text: str) -> str:
    """Convert a limited markdown subset to HTML.

    Handles: h1-h4, paragraphs, bold, italic, inline code, fenced code
    blocks, unordered/ordered lists, links, images (→ alt text), hr,
    blockquotes, and tables.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            code_escaped = html_module.escape("\n".join(code_lines))
            lang_attr = f' class="language-{html_module.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{lang_attr}>{code_escaped}\n</code></pre>")
            continue

        # Horizontal rule
        if re.match(r"^-{3,}\s*$", line) or re.match(r"^\*{3,}\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        # ATX headers
        h_match = re.match(r"^(#{1,4})\s+(.+?)\s*#*$", line)
        if h_match:
            level = len(h_match.group(1))
            content = _inline_md(h_match.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            bq_lines: list[str] = []
            while i < n and lines[i].startswith("> "):
                bq_lines.append(lines[i][2:])
                i += 1
            bq_html = _md_to_html("\n".join(bq_lines))
            out.append(f"<blockquote>{bq_html}</blockquote>")
            continue

        # Unordered list
        if re.match(r"^[-*+]\s", line):
            items, i = _parse_list(lines, i, r"^[-*+]\s")
            list_html = "".join(f"<li>{_inline_md(item)}</li>" for item in items)
            out.append(f"<ul>{list_html}</ul>")
            continue

        # Ordered list
        if re.match(r"^\d+\.\s", line):
            items, i = _parse_list(lines, i, r"^\d+\.\s")
            list_html = "".join(f"<li>{_inline_md(item)}</li>" for item in items)
            out.append(f"<ol>{list_html}</ol>")
            continue

        # Table
        if "|" in line and i + 1 < n and re.match(r"^\|[\s:-]+\|", lines[i + 1]):
            table_html, i = _parse_table(lines, i)
            out.append(table_html)
            continue

        # Indented code block (4 spaces) — only when content is non-whitespace
        if (line.startswith("    ") or line.startswith("\t")) and line.strip():
            code_lines, i = _collect_indented_code(lines, i)
            if code_lines:
                code_escaped = html_module.escape("\n".join(code_lines))
                out.append(f"<pre><code>{code_escaped}\n</code></pre>")
            continue

        # Whitespace-only indented line — treat as paragraph separator
        if (line.startswith("    ") or line.startswith("\t")) and not line.strip():
            i += 1
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Paragraph (collect consecutive non-empty lines)
        para_lines: list[str] = []
        while i < n:
            l = lines[i]
            if not l.strip():
                break
            if re.match(r"^(#{1,4}\s|```|---|\*{3,}|\d+\.\s|[-*+]\s|>\s|\|)", l):
                break
            para_lines.append(l)
            i += 1
        para = " ".join(p.strip() for p in para_lines if p.strip())
        if para:
            out.append(f"<p>{_inline_md(para)}</p>")
        continue

    return "\n".join(out)


def _collect_indented_code(lines: list[str], start: int) -> Tuple[List[str], int]:
    """Collect lines of an indented code block starting at *start*.

    Returns (code_lines, next_index).  Whitespace-only lines within the
    block are preserved; a block whose *only* content is whitespace
    returns an empty list.
    """
    code_lines: list[str] = []
    # Include the first line
    if lines[start].strip():
        code_lines.append(lines[start])
    i = start + 1
    n = len(lines)
    while i < n and (lines[i].startswith("    ") or lines[i].startswith("\t") or lines[i] == ""):
        if lines[i].strip() or code_lines:
            code_lines.append(lines[i])
        i += 1
    # If the block never had real content, discard it
    if not any(ln.strip() for ln in code_lines):
        return [], start + 1
    return code_lines, i


def _inline_md(text: str) -> str:
    """Convert inline markdown within a paragraph/heading.

    Each pattern independently HTML-escapes its captured content, so no
    global pre-escape is needed.  This avoids double-escaping issues
    (e.g. `` `a < b` `` → ``<code>a &lt; b</code>``, not ``&amp;lt;``).
    """
    # Image: ![alt](url) → alt text
    text = re.sub(
        r"!\[([^\]]*)\]\([^)]+\)",
        lambda m: html_module.escape(m.group(1) or ""),
        text,
    )

    # Link: [text](url) → <a href="url">text</a>
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html_module.escape(m.group(2))}">{html_module.escape(m.group(1))}</a>',
        text,
    )

    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<strong>{html_module.escape(m.group(1))}</strong>",
        text,
    )
    text = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
        lambda m: f"<em>{html_module.escape(m.group(1))}</em>",
        text,
    )
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{html_module.escape(m.group(1))}</code>",
        text,
    )
    text = re.sub(
        r"~~(.+?)~~",
        lambda m: f"<s>{html_module.escape(m.group(1))}</s>",
        text,
    )
    return text


def _parse_list(lines: list[str], start: int, pattern: str) -> Tuple[List[str], int]:
    """Collect list items starting at *start* matching *pattern*."""
    items: list[str] = []
    i = start
    while i < len(lines):
        m = re.match(pattern, lines[i])
        if m:
            item = lines[i][m.end():].strip()
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|```|\d+\.\s|[-*+]\s)", lines[i]
            ):
                item += " " + lines[i].strip()
                i += 1
            items.append(item)
        else:
            break
    return items, i


def _parse_table(lines: list[str], start: int) -> Tuple[str, int]:
    """Parse a markdown table starting at *start*."""
    header_line = lines[start]
    i = start + 2  # skip separator line

    headers = [c.strip() for c in header_line.strip().strip("|").split("|")]
    rows: list[str] = []
    while i < len(lines) and "|" in lines[i]:
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        cells_html = "".join(f"<td>{_inline_md(c)}</td>" for c in cells)
        rows.append(f"<tr>{cells_html}</tr>")
        i += 1

    headers_html = "".join(f"<th>{_inline_md(h)}</th>" for h in headers)
    table = f"<table><thead><tr>{headers_html}</tr></thead><tbody>"
    table += "".join(rows)
    table += "</tbody></table>"
    return table, i
