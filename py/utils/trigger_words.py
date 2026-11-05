"""Helpers for reading trigger words out of a model's ``civitai`` metadata.

Trigger words live in ``civitai.trainedWords`` no matter where the model came
from: CivitAI/CivArchive sync, a HuggingFace/ModelScope model card, the AI
metadata-enrichment skill, or a manual edit in the model modal. Readers must
accept the loose shapes older sidecars can contain (``None``, a bare string, a
list holding non-string entries) instead of assuming a clean list, which is
also why this lives here rather than repeated at every call site.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping


def iter_trigger_words(civitai: Any) -> Iterator[str]:
    """Yield the non-empty trigger words declared in a ``civitai`` block.

    Internal whitespace is collapsed so a sidecar holding ``"anime\nstyle"``
    still matches an ``"anime style"`` query. Declaration order and duplicates
    are preserved; callers that need a set can build one themselves.
    """
    if not isinstance(civitai, Mapping):
        return

    words = civitai.get("trainedWords")
    if isinstance(words, str):
        words = [words]
    if not isinstance(words, (list, tuple)):
        return

    for word in words:
        if not isinstance(word, str):
            continue
        normalized = " ".join(word.split())
        if normalized:
            yield normalized


__all__ = ["iter_trigger_words"]
