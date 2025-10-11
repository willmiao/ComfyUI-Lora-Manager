"""Helpers for parsing and resolving priority tag configurations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class PriorityTagEntry:
    """A parsed priority tag configuration entry."""

    canonical: str
    aliases: Set[str]

    @property
    def normalized_aliases(self) -> Set[str]:
        return {alias.lower() for alias in self.aliases}


def _normalize_alias(alias: str) -> str:
    return alias.strip()


def parse_priority_tag_string(config: str | None) -> List[PriorityTagEntry]:
    """Parse the user-facing priority tag string into structured entries."""

    if not config:
        return []

    entries: List[PriorityTagEntry] = []
    seen_canonicals: Set[str] = set()

    for raw_entry in _split_priority_entries(config):
        canonical, aliases = _parse_priority_entry(raw_entry)
        if not canonical:
            continue

        normalized_canonical = canonical.lower()
        if normalized_canonical in seen_canonicals:
            # Skip duplicate canonicals while preserving first occurrence priority
            continue
        seen_canonicals.add(normalized_canonical)

        alias_set = {canonical, *aliases}
        cleaned_aliases = {_normalize_alias(alias) for alias in alias_set if _normalize_alias(alias)}
        if not cleaned_aliases:
            continue

        entries.append(PriorityTagEntry(canonical=canonical, aliases=cleaned_aliases))

    return entries


def _split_priority_entries(config: str) -> List[str]:
    # Split on commas while respecting that users may add new lines for readability
    parts = []
    for chunk in config.split('\n'):
        parts.extend(chunk.split(','))
    return [part.strip() for part in parts if part.strip()]


def _parse_priority_entry(entry: str) -> tuple[str, Set[str]]:
    if '(' in entry and entry.endswith(')'):
        canonical, raw_aliases = entry.split('(', 1)
        canonical = canonical.strip()
        alias_section = raw_aliases[:-1]  # drop trailing ')'
        aliases = {alias.strip() for alias in alias_section.split('|') if alias.strip()}
        return canonical, aliases

    if '(' in entry and not entry.endswith(')'):
        # Malformed entry; treat as literal canonical to avoid surprises
        entry = entry.replace('(', '').replace(')', '')

    canonical = entry.strip()
    return canonical, set()


def resolve_priority_tag(
    tags: Sequence[str] | Iterable[str],
    entries: Sequence[PriorityTagEntry],
) -> Optional[str]:
    """Resolve the first matching canonical priority tag for the provided tags."""

    tag_lookup: Dict[str, str] = {}
    for tag in tags:
        if not isinstance(tag, str):
            continue
        normalized = tag.lower()
        if normalized not in tag_lookup:
            tag_lookup[normalized] = tag

    for entry in entries:
        for alias in entry.normalized_aliases:
            if alias in tag_lookup:
                return entry.canonical

    return None


def collect_canonical_tags(entries: Iterable[PriorityTagEntry]) -> List[str]:
    """Return the ordered list of canonical tags from the parsed entries."""

    return [entry.canonical for entry in entries]
