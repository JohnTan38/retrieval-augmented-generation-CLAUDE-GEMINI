"""Citation parsing deliberately limited to presented source identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Collection


_CITATION = re.compile(r"\[S([1-9][0-9]*)\]")


@dataclass(frozen=True)
class CitationResult:
    cited_source_ids: list[str]
    valid: bool


def validate_citations(answer: str, supplied_ids: Collection[str]) -> CitationResult:
    """Return citations in first-seen order and reject only well-formed unknown IDs."""
    seen: set[str] = set()
    cited: list[str] = []
    valid = True
    for match in _CITATION.finditer(answer):
        source_id = f"S{match.group(1)}"
        if source_id not in supplied_ids:
            valid = False
        elif source_id not in seen:
            seen.add(source_id)
            cited.append(source_id)
    return CitationResult(cited_source_ids=cited, valid=valid)
