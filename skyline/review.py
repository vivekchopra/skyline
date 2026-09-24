"""Review order from ADR 0001.

1. New policy violations (already on the diff)
2. Breaking public signature / heritage / schema changes
3. High CRAP on added and body-modified units
4. New coupling that is legal
5. Untested new types
6. Everything else
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

_BODY_ONLY = ("body changed",)
_TOP_N = 5

HOW_TO_REVIEW = (
    "Policy violations first: new dependencies skyline.policy.toml forbids. Nothing listed means this change is allowed, or the repo has no policy.",
    "Then breaking public signatures, inheritance, and schema. Dependents are other files that import the changed file; read a break with dependents first.",
    "CRAP marks added or modified code that is complex and untested, which is where a defect is most likely. complexity\u00b2 \u00d7 (1 \u2212 coverage)\u00b3 + complexity. \u22645 low, \u226410 moderate, \u226430 high, >30 severe. No coverage file counts as 0%. A high score is a place to read, not a failed check.",
    "Then new imports that are allowed. A thicker arrow is a two-way import.",
    "Then new types whose names do not appear in a changed test file.",
    "Green is added, red removed, orange modified, grey an unchanged neighbor. The diagram is that neighborhood, not the whole repo. The second diagram is tables and columns.",
)


@dataclass
class Review:
    caption: str
    breaking: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    coupling: List[str] = field(default_factory=list)
    untested: List[str] = field(default_factory=list)
    chips: Dict[str, List[str]] = field(default_factory=dict)


def build_review(diff, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> Review:
    review = Review(caption=_caption(diff, base_sources, head_sources))
    review.breaking = _breaking(diff)
    review.risks = _risks(diff)
    review.coupling = _legal_coupling(diff)
    review.untested = _untested(diff, base_sources, head_sources)
    review.chips = _chips(diff, review)
    return review


def _caption(diff, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> str:
    paths = set(base_sources) | set(head_sources)
    changed = sum(1 for path in paths if base_sources.get(path) != head_sources.get(path))
    counts = diff.counts()
    file_word = "file" if changed == 1 else "files"
    parts = [f"{changed} {file_word} changed"]
    parts.append(
        f"types +{counts['types_added']} -{counts['types_removed']} ~{counts['types_modified']}"
    )
    violations = [v for v in getattr(diff, "violations", []) if getattr(v, "is_new", False)]
    if violations:
        parts.append(f"{len(violations)} policy violation(s)")
    return " \u00b7 ".join(parts)


def _is_body_only(reason: str) -> bool:
    parts = [part.strip() for part in reason.split(";") if part.strip()]
    if not parts:
        return True
    return all(part in _BODY_ONLY or part.startswith("complexity ") for part in parts)


def _fan_in_by_file(diff) -> Dict[str, int]:
    """Other files that import each file. Head edges win; a deleted file keeps its old importers."""
    head: Dict[str, set] = {}
    base: Dict[str, set] = {}
    for imp in diff.imports:
        if imp.status in ("added", "unchanged"):
            head.setdefault(imp.target, set()).add(imp.source)
        if imp.status in ("removed", "unchanged"):
            base.setdefault(imp.target, set()).add(imp.source)
    counts = {}
    for path in set(head) | set(base):
        live = head.get(path) or set()
        counts[path] = len(live) if live else len(base.get(path) or set())
    return counts


def _dependent_clause(path: str, fan_in: Dict[str, int]) -> str:
    count = fan_in.get(path, 0)
    if count <= 0:
        return ""
    word = "dependent" if count == 1 else "dependents"
    return f" \u00b7 {count} {word}"


def _file_of(qualname: str) -> str:
    return qualname.split("::", 1)[0]


def _breaking(diff) -> List[str]:
    fan_in = _fan_in_by_file(diff)
    ranked = []
    order = 0

    def add(path: str, line: str) -> None:
        nonlocal order
        ranked.append((fan_in.get(path, 0), order, line + _dependent_clause(path, fan_in)))
        order += 1

    for type_change in diff.types:
        if not type_change.exported:
            continue
        path = _file_of(type_change.qualname)
        if type_change.status == "removed":
            add(path, f"removed {type_change.kind} {type_change.qualname}")
        elif type_change.added_relations or type_change.removed_relations or not _is_body_only(type_change.reason):
            if type_change.status == "modified":
                add(path, f"breaking {type_change.kind} {type_change.qualname}")
        for member in type_change.members:
            unit = member.after or member.before
            if unit is None or not unit.exported:
                continue
            if member.status == "removed":
                add(path, f"removed {type_change.qualname}.{member.name}")
            elif member.status == "modified" and not _is_body_only(member.reason):
                add(path, f"breaking {type_change.qualname}.{member.name}: {member.reason}")
    for fn in diff.functions:
        unit = fn.after or fn.before
        if unit is None or not unit.exported:
            continue
        path = _file_of(fn.qualname)
        if fn.status == "removed":
            add(path, f"removed {fn.qualname}")
        elif fn.status == "modified" and not _is_body_only(fn.reason):
            add(path, f"breaking {fn.qualname}: {fn.reason}")
    for table in diff.tables:
        if table.status == "removed":
            add("", f"removed table {table.qualname}")
        for column in table.columns:
            if column.status == "removed":
                add("", f"removed column {table.qualname}.{column.name}")
            elif column.status == "modified":
                add("", f"breaking column {table.qualname}.{column.name}")
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [line for _, _, line in ranked]


def _risks(diff) -> List[str]:
    scored = []
    for type_change in diff.types:
        for member in type_change.members:
            if member.crap is None or member.status not in ("added", "modified"):
                continue
            scored.append((member.crap.value, f"{type_change.qualname}.{member.name}", member.crap.label()))
    for fn in diff.functions:
        if fn.crap is None or fn.status not in ("added", "modified"):
            continue
        scored.append((fn.crap.value, fn.qualname, fn.crap.label()))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [f"{name} {label}" for _, name, label in scored[:_TOP_N]]


def _legal_coupling(diff) -> List[str]:
    illegal = {
        (v.source, v.target)
        for v in getattr(diff, "violations", [])
        if getattr(v, "kind", "") == "illegal_edge"
    }
    lines = []
    for imp in diff.imports:
        if imp.status != "added" or (imp.source, imp.target) in illegal:
            continue
        lines.append(f"{imp.source} \u2192 {imp.target}")
    return lines


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return True
    return path.startswith(("tests/", "test/")) or "/tests/" in f"/{path}" or "/test/" in f"/{path}"


def _untested(diff, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> List[str]:
    blobs = []
    for path, source in head_sources.items():
        if _is_test_path(path) and base_sources.get(path) != source:
            blobs.append(source)
    blob = "\n".join(blobs)
    missing = []
    for type_change in diff.types:
        if type_change.status != "added":
            continue
        if re.search(rf"\b{re.escape(type_change.name)}\b", blob):
            continue
        missing.append(type_change.qualname)
    return missing


def _add_chip(chips: Dict[str, List[str]], key: str, label: str) -> None:
    chips.setdefault(key, [])
    if label not in chips[key]:
        chips[key].append(label)


def _chips(diff, review: Review) -> Dict[str, List[str]]:
    chips: Dict[str, List[str]] = {}
    breaking_keys = set()
    for type_change in diff.types:
        if type_change.exported and (
            type_change.status == "removed"
            or (
                type_change.status == "modified"
                and (type_change.added_relations or type_change.removed_relations
                     or not _is_body_only(type_change.reason))
            )
        ):
            breaking_keys.add(type_change.qualname)
        for member in type_change.members:
            unit = member.after or member.before
            key = f"{type_change.qualname}.{member.name}"
            if type_change.exported and unit is not None and unit.exported and (
                member.status == "removed" or (member.status == "modified" and not _is_body_only(member.reason))
            ):
                breaking_keys.add(key)
            if member.crap is not None and member.crap.band in ("high", "severe"):
                _add_chip(chips, key, member.crap.band)
            if member.status == "modified" and _is_body_only(member.reason):
                _add_chip(chips, key, "body")
    for key in breaking_keys:
        _add_chip(chips, key, "breaking")
    for qualname in review.untested:
        _add_chip(chips, qualname, "untested")
    return chips
