"""Citation parsing deliberately limited to presented source identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Collection


_CITATION_MARKER = re.compile(r"\[S[^\]]*\]")
_VALID_CITATION_MARKER = re.compile(r"\[S[1-9][0-9]*(?:\s*,\s*S[1-9][0-9]*)*\]")
_CITATION_ID = re.compile(r"S[1-9][0-9]*")


@dataclass(frozen=True)
class CitationResult:
    cited_source_ids: list[str]
    valid: bool


def validate_citations(answer: str, supplied_ids: Collection[str]) -> CitationResult:
    """Return cited IDs in first-seen order, accepting individual or grouped markers."""
    seen: set[str] = set()
    cited: list[str] = []
    valid = bool(answer.strip())
    for marker in _CITATION_MARKER.finditer(answer):
        marker_text = marker.group(0)
        if not _VALID_CITATION_MARKER.fullmatch(marker_text):
            valid = False
            continue
        for source_id in _CITATION_ID.findall(marker_text):
            if source_id not in supplied_ids:
                valid = False
            elif source_id not in seen:
                seen.add(source_id)
                cited.append(source_id)
    if not cited:
        valid = False
    return CitationResult(cited_source_ids=cited, valid=valid)
