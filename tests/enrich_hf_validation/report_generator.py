"""Generate structured reports from evaluation results.

Produces:

1. A JSON data dump (``report.json``) with all scores and aggregations.
2. A human-readable Markdown report (``report.md``) with summary stats,
   issue patterns, and actionable optimisation suggestions.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from .evaluation_engine import ScoreRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def _bar(value: float, width: int = 20) -> str:
    filled = int(round(value / 100 * width))
    return "█" * filled + "░" * (width - filled)


def generate_optimisation_suggestions(
    agg: Dict[str, Any],
    scores: List[ScoreRecord],
) -> List[str]:
    """Analyse evaluation results and produce concrete suggestions."""
    suggestions: List[str] = []
    fa = agg.get("field_aggregates", {})

    # --- base_model ---
    bm = fa.get("base_model", {})
    if bm and bm.get("empty_rate_pct", 0) > 30:
        suggestions.append(
            "- **base_model 空置率高 ({:.0f}%)**: 多数 HF 模型卡片未在 YAML frontmatter 中声明 "
            "`base_model:` 字段，LLM 无法推断。可考虑在 prompt 中增加 \"look at the model file name "
            "for clues\" 的引导，或在后处理中增加基于文件名规则的 fallback 猜测。".format(
                bm.get("empty_rate_pct", 0)
            )
        )
    bm_invalid = sum(
        1
        for s in scores
        if s["raw_values"]["base_model"]
        and s["raw_values"]["base_model"] != "Unknown"
        and s["raw_values"]["base_model"] not in {
            "SD 1.4", "SD 1.5", "SD 1.5 LCM", "SD 1.5 Hyper",
            "SD 2.0", "SD 2.1", "SD 3", "SD 3.5", "SD 3.5 Medium",
            "SD 3.5 Large", "SD 3.5 Large Turbo",
            "SDXL 1.0", "SDXL Lightning", "SDXL Hyper",
            "Flux.1 D", "Flux.1 S", "Flux.1 Krea", "Flux.1 Kontext",
            "Flux.2 D", "Flux.2 Klein 9B", "Flux.2 Klein 9B-base",
            "Flux.2 Klein 4B", "Flux.2 Klein 4B-base",
            "AuraFlow", "Chroma", "PixArt a", "PixArt E",
            "Hunyuan 1", "Lumina", "Kolors",
            "NoobAI", "Illustrious", "Pony", "Pony V7",
            "HiDream", "Qwen", "ZImageTurbo", "ZImageBase",
            "SVD", "LTXV", "LTXV2", "LTXV 2.3",
            "CogVideoX", "Mochi",
            "Wan Video", "Wan Video 1.3B t2v", "Wan Video 14B t2v",
            "Wan Video 14B i2v 480p", "Wan Video 14B i2v 720p",
            "Wan Video 2.2 TI2V-5B", "Wan Video 2.2 T2V-A14B",
            "Wan Video 2.2 I2V-A14B",
            "Wan Video 2.5 T2V", "Wan Video 2.5 I2V",
            "Hunyuan Video", "Anima", "Ernie", "Ernie Turbo",
            "Nucleus", "Krea 2",
        }
    )
    if bm_invalid > 5:
        suggestions.append(
            "- **base_model 含非标准值 ({} 个)**: LLM 输出了未在 `SUPPORTED_DOWNLOAD_SKIP_BASE_MODELS` "
            "中的 base model 名称。建议在 prompt 中强调 \"Use EXACTLY one name from the list\" 并在 "
            "`PostProcessor` 中加一层验证过滤，非标准值直接丢弃。".format(bm_invalid)
        )

    # --- trigger_words ---
    tw = fa.get("trigger_words", {})
    if tw and tw.get("empty_rate_pct", 0) > 40:
        suggestions.append(
            "- **trigger_words 空置率高 ({:.0f}%)**: 大量 HF 模型卡没有明确的 "
            "`instance_prompt:` 或 trigger word 说明。当前 prompt 已覆盖常见模式。若确认这些模型确实"
            "没有 trigger words（例如 style lora），空数组是正确结果，不需优化。".format(
                tw.get("empty_rate_pct", 0)
            )
        )

    # --- tags ---
    tag = fa.get("tags", {})
    if tag and tag.get("empty_rate_pct", 0) > 30:
        suggestions.append(
            "- **tags 空置率高 ({:.0f}%)**: 当前 prompt 要求 tags 必须与 "
            "`priority_tags`（CIVITAI_MODEL_TAGS）对齐。HF 模型的标签体系与 Civitai 不同，"
            "很多 model card 使用细粒度标签（如 `pokemon`、`watercolor`）而不在 priority list 中。"
            "建议: 扩大 priority_tags 范围，或允许 LLM 自由生成 tags 后只做去重不做严格过滤。".format(
                tag.get("empty_rate_pct", 0)
            )
        )

    # --- tags priority coverage ---
    low_coverage = sum(
        1
        for s in scores
        if s["field_scores"].get("tags_priority_coverage", 5) < 3  # < 60% of max
        and s["field_scores"].get("tags", 0) > 0
    )
    if low_coverage > 10:
        suggestions.append(
            "- **{} 个模型的 tags 与 priority_tags 匹配度低于 60%**: "
            "LLM 生成了有意义但不属于 CIVITAI_MODEL_TAGS 的标签。这说明 priority_tags "
            "的覆盖范围对 HF 模型不足，建议按 HF 模型的实际分布补充新类别。".format(low_coverage)
        )

    # --- preview ---
    prev = fa.get("preview_downloaded", {})
    if prev and prev.get("empty_rate_pct", 0) > 50:
        suggestions.append(
            "- **预览图下载成功率低 ({:.0f}%)**: 很多 HF 模型卡没有 embed 图片（仅使用 YAML widget "
            "或 external link）。当前 `md_to_html.py` 的 `extract_gallery_images` 和 "
            "`extract_gallery_table_images` 已覆盖了多数场景。若预览图不重要，可降低此字段权重。".format(
                prev.get("empty_rate_pct", 0)
            )
        )

    # --- usage_tips ---
    ut = fa.get("usage_tips", {})
    if ut and ut.get("empty_rate_pct", 0) > 70:
        suggestions.append(
            "- **usage_tips 空置率极高 ({:.0f}%)**: 这是预期行为。HF 模型卡通常不包含 LoRA "
            "强度/CLIP skip 等结构化参数。当前提取策略已合理。若需要可用数据，" "可以考虑使用模型类型的通用默认值。".format(
                ut.get("empty_rate_pct", 0)
            )
        )

    # --- short_description ---
    sd = fa.get("short_description", {})
    if sd and sd.get("empty_rate_pct", 0) > 40:
        suggestions.append(
            "- **short_description 空置率 ({:.0f}%)**: 部分 HF 模型卡 README 内容极少（仅含标签和训练参数）。".format(
                sd.get("empty_rate_pct", 0)
            )
        )

    if not suggestions:
        suggestions.append("- 未发现明显问题模式，各字段填充率均在可接受范围。")

    return suggestions


def generate_markdown_report(
    agg: Dict[str, Any],
    scores: List[ScoreRecord],
    output_dir: str,
    duration_summary: Dict[str, Any] | None = None,
) -> str:
    """Write ``report.md`` and return its content."""
    lines: List[str] = []
    def wl(text: str = "") -> None:
        lines.append(text)

    wl("# HF Metadata Enrichment Validation Report")
    wl()
    wl(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    wl(f"Models evaluated: **{agg.get('model_count', 0)}**")
    wl(f"Successful enrichments: **{agg.get('success_count', 0)}**")
    wl(f"Failures: **{agg.get('fail_count', 0)}**")
    wl()

    # ---- Duration ----
    if duration_summary:
        wl("## Timing")
        wl()
        wl(f"- Total wall time: **{duration_summary.get('total_wall_s', 0):.0f} s** ")
        wl(f"  ({duration_summary.get('total_wall_s', 0) / 60:.1f} min)")
        wl(f"- Mean per model: **{duration_summary.get('mean_s', 0):.1f} s**")
        wl(f"- Median per model: **{duration_summary.get('median_s', 0):.1f} s**")
        wl(f"- Fastest: **{duration_summary.get('min_s', 0):.1f} s**")
        wl(f"- Slowest: **{duration_summary.get('max_s', 0):.1f} s**")
        wl()

    # ---- Overall score ----
    ts = agg.get("total_score", {})
    wl("## Overall Score Distribution  (0–100)")
    wl()
    wl(f"| Metric | Value |")
    wl(f"|--------|-------|")
    wl(f"| Mean   | {ts.get('mean', 'N/A')} |")
    wl(f"| Median | {ts.get('median', 'N/A')} |")
    wl(f"| Min    | {ts.get('min', 'N/A')} |")
    wl(f"| Max    | {ts.get('max', 'N/A')} |")
    wl()
    for label, key in [
        ("Excellent (≥80)", "excellent_80+"),
        ("Good (60–79)", "good_60_79"),
        ("Fair (40–59)", "fair_40_59"),
        ("Poor (20–39)", "poor_20_39"),
        ("Bad (<20)", "bad_0_19"),
    ]:
        count = ts.get("bins", {}).get(key, 0)
        pct = count / agg["model_count"] * 100 if agg["model_count"] else 0
        wl(f"- **{label}**: {count} models ({_fmt_pct(pct)})")
    wl()

    # ---- Per-field aggregates ----
    wl("## Per-Field Completeness")
    wl()
    wl("| Field | Mean Score | Fill Rate | Empty Rate |")
    wl("|-------|-----------:|----------:|-----------:|")
    fa = agg.get("field_aggregates", {})
    for fn in [
        "base_model", "trigger_words", "short_description", "tags",
        "tags_priority_coverage", "notes", "usage_tips",
        "modelDescription_html", "preview_downloaded",
    ]:
        f = fa.get(fn, {})
        if not f:
            continue
        wl(
            f"| {fn} "
            f"| {f.get('mean', 'N/A')} "
            f"| {_fmt_pct(f.get('fill_rate_pct', 0))} "
            f"| {_fmt_pct(f.get('empty_rate_pct', 0))} |"
        )
    wl()

    # ---- Confidence distribution ----
    wl("## LLM Confidence Distribution")
    wl()
    cd = agg.get("confidence_distribution", {})
    total_conf = sum(cd.values()) or 1
    for level in ["high", "medium", "low", ""]:
        count = cd.get(level, 0)
        label = level if level else "(not reported)"
        pct = count / total_conf * 100
        bar = _bar(pct)
        wl(f"- **{label}**: {count}  {bar}  {_fmt_pct(pct)}")
    wl()

    # ---- Top issues ----
    wl("## Most Frequent Issues")
    wl()
    for issue, count in agg.get("top_issues", []):
        pct = count / agg["model_count"] * 100 if agg["model_count"] else 0
        wl(f"- **{issue}** — {count}/{agg['model_count']} ({_fmt_pct(pct)})")
    wl()

    # ---- Optimisation suggestions ----
    wl("## Optimisation Suggestions")
    wl()
    suggestions = generate_optimisation_suggestions(agg, scores)
    for s in suggestions:
        wl(s)
    wl()

    # ---- Per-model detail ----
    wl("## Per-Model Detail")
    wl()
    wl("<details>")
    wl("<summary>Click to expand</summary>")
    wl()
    wl("| # | Repo ID | Score | Issues | Confidence |")
    wl("|---|---------|------:|--------|------------|")
    for i, s in enumerate(scores, 1):
        issue_count = len(s["issues"])
        issue_str = (
            f"{issue_count} issue(s)" if issue_count else "✓ ok"
        )
        wl(
            f"| {i} "
            f"| {s['repo_id']} "
            f"| {s['total_score']} "
            f"| {issue_str} "
            f"| {s.get('confidence_from_llm', '') or '-'} |"
        )
    wl()
    wl("</details>")
    wl()

    content = "\n".join(lines)
    report_path = os.path.join(output_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    logger.info("Markdown report written to %s", report_path)
    return content


# ---------------------------------------------------------------------------
# JSON dump
# ---------------------------------------------------------------------------


def save_json_report(
    agg: Dict[str, Any],
    scores: List[ScoreRecord],
    enrichment_results: List[Dict[str, Any]],
    output_dir: str,
    duration_summary: Dict[str, Any] | None = None,
) -> str:
    """Write ``report.json`` and return the path."""
    report: Dict[str, Any] = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "model_count": agg.get("model_count", 0),
        },
        "aggregate": agg,
        "timing": duration_summary or {},
        "per_model_scores": scores,
        "enrichment_results": enrichment_results,
    }
    path = os.path.join(output_dir, "report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    logger.info("JSON report written to %s", path)
    return path
