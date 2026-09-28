"""Hunk size and complexity of the added lines, not of the whole function."""
from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Sequence, Tuple

# Decision points on the lines this pull request added. A fragment does not
# start at 1: the count is the complexity the hunk introduced.
_DECISION = re.compile(r"\b(if|elif|for|while|except|case|catch)\b|\b(and|or)\b|&&|\|\|")

SMALL_HUNK = 8


def decision_count(lines: Sequence[str]) -> int:
    return sum(len(_DECISION.findall(line)) for line in lines)


def line_delta(before: Sequence[str], after: Sequence[str]) -> Tuple[int, int, List[str], List[str]]:
    added = removed = 0
    added_lines: List[str] = []
    removed_lines: List[str] = []
    matcher = difflib.SequenceMatcher(a=list(before), b=list(after))
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
            removed_lines.extend(before[i1:i2])
        if tag in ("replace", "insert"):
            added += j2 - j1
            added_lines.extend(after[j1:j2])
    return added, removed, added_lines, removed_lines


def whitespace_only(added: Sequence[str], removed: Sequence[str]) -> bool:
    def norm(lines: Sequence[str]) -> str:
        return "\n".join(" ".join(line.split()) for line in lines if line.strip())

    if not added and not removed:
        return False
    return norm(added) == norm(removed)


def slice_lines(source: str, line: Optional[int], end_line: Optional[int]) -> List[str]:
    if not source or not line:
        return []
    rows = source.splitlines()
    start = max(line - 1, 0)
    stop = end_line if end_line else line
    return rows[start:max(stop, start)]


def head_hunk_lines(base: str, head: str) -> set:
    """1-based head line numbers that sit inside a diff hunk."""
    if base == head:
        return set()
    if not base:
        return set(range(1, len(head.splitlines()) + 1))
    before = base.splitlines()
    after = head.splitlines()
    lines = set()
    matcher = difflib.SequenceMatcher(a=before, b=after)
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            for offset in range(j1, j2):
                lines.add(offset + 1)
    return lines


def hunk_map(base_sources: Dict[str, str], head_sources: Dict[str, str]) -> Dict[str, set]:
    paths = set(base_sources) | set(head_sources)
    return {
        path: head_hunk_lines(base_sources.get(path, ""), head_sources.get(path, ""))
        for path in paths
        if base_sources.get(path) != head_sources.get(path)
    }


def cite(path: str, line: Optional[int], end_line: Optional[int], hunks: Dict[str, set]) -> Tuple[Optional[int], Optional[int]]:
    """A source line on the head commit inside a hunk, or nothing."""
    if not path or path not in hunks or line is None:
        return None, None
    last = end_line if end_line else line
    overlap = [number for number in range(line, last + 1) if number in hunks[path]]
    if not overlap:
        return None, None
    return overlap[0], overlap[-1]


def measure_deltas(diff, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> None:
    """Fill lines added, lines removed, and complexity of the added lines."""
    for type_change in diff.types:
        for member in type_change.members:
            if member.status not in ("added", "modified"):
                continue
            _measure_unit(member, type_change.path, base_sources, head_sources)
    for fn in diff.functions:
        if fn.status not in ("added", "modified"):
            continue
        _measure_unit(fn, fn.path, base_sources, head_sources)


def _measure_unit(change, path: str, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> None:
    after = getattr(change, "after", None)
    before = getattr(change, "before", None)
    after_lines = slice_lines(
        head_sources.get(path, ""),
        getattr(after, "line", None),
        getattr(after, "end_line", None),
    )
    before_lines = slice_lines(
        base_sources.get(path, ""),
        getattr(before, "line", None),
        getattr(before, "end_line", None),
    )
    if change.status == "added":
        added, removed, added_lines, removed_lines = len(after_lines), 0, list(after_lines), []
        complexity = getattr(after, "complexity", None)
        added_complexity = complexity if complexity is not None else decision_count(added_lines)
    else:
        added, removed, added_lines, removed_lines = line_delta(before_lines, after_lines)
        added_complexity = decision_count(added_lines)
    change.lines_added = added
    change.lines_removed = removed
    change.added_complexity = added_complexity
    change.whitespace = whitespace_only(added_lines, removed_lines)
    change.delta_measured = True


def is_small_hunk(change) -> bool:
    return (getattr(change, "lines_added", 0) + getattr(change, "lines_removed", 0)) <= SMALL_HUNK
