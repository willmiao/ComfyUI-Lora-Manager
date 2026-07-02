"""Inline markdown-to-HTML converter for HF README content.

No external dependencies.  Strips YAML frontmatter, ``<Gallery />`` sections,
badge images, and HTML comments before rendering.  Only used by the
``enrich_hf_metadata`` skill.
"""

from __future__ import annotations

import html as html_module
import re
from typing import List, Tuple


_REPO_URL_PATTERN = re.compile(r"https?://huggingface\.co/([^/]+/[^/]+)")


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

    # Split entries starting with `- text:`
    entries = re.split(r"\n- text:", frontmatter[widget_match.end():])
    for entry in entries:
        if not entry.strip():
            continue

        entry = entry.strip()

        # Extract text (prompt)
        text = ""
        # Quoted inline: `"some prompt"`
        qm = re.match(r'^"((?:[^"\\]|\\.)*)"', entry)
        if qm:
            text = qm.group(1)
        else:
            # Multi-line YAML scalar: `>-\n    line1\n    line2`
            mm = re.match(r"^>(?:-\s*)?\n((?:.+(?:\n|$))+)", entry, re.MULTILINE)
            if mm:
                raw = mm.group(1)
                # Take lines until a line starts with a YAML key (word + colon)
                text_lines: list[str] = []
                for line in raw.split("\n"):
                    if re.match(r"^\s*\w+:", line):
                        break
                    text_lines.append(line)
                text = " ".join(
                    line.strip() for line in text_lines if line.strip()
                )

        # Extract output.url
        url = ""
        url_match = re.search(
            r"^\s*output:\s*\n\s+url:\s*(.+?)\s*$", entry, re.MULTILINE
        )
        if url_match:
            raw_path = url_match.group(1).strip().strip("'\"")
            if raw_path and not raw_path.startswith("http"):
                url = f"{base_url}/{raw_path.lstrip('/')}"
            elif raw_path.startswith("http"):
                url = raw_path

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
# Pre-processing: strip unwanted sections
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
