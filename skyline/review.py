"""One review model for the comment, the HTML page, and the agent prompt.

The two ranked lists are the change, not the size of the function that was
already there:

1. Changed behavior: new units, and units whose added complexity is high.
2. Hotspots touched: an existing function with a small hunk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import crap
from .delta import cite, hunk_map, is_small_hunk, measure_deltas
from .noise import is_generated, strip_generated

_BODY_ONLY = ("body changed",)
SECTION_CAP = 15

HOW_TO_REVIEW = (
    "This is architecture drift. A high score is a place to read. It is not a defect.",
    "Policy violations first: new dependencies skyline.policy.toml forbids. Nothing listed means this change is allowed, or the repo has no policy.",
    "Then semantic schema changes: a new table, a new or removed column, and whether the writers are new or already there. Column alignment is not a change.",
    "Then changed behavior: new units, and units whose added complexity is high. Highest delta first.",
    "Then hotspots touched: a pre-existing function with a small hunk. The hunk size is the change. The function's old complexity is not.",
    "Then service files with no sibling test in this diff. A DTO, an Args type, or a payload enum is not a missing test.",
    "Green is added, red removed, orange modified, grey an unchanged neighbor. The diagram is the hand-written neighborhood, not generated clients.",
)


@dataclass
class Finding:
    """One review row. ``side`` is the commit the link should open."""
    text: str
    path: str = ""
    line: Optional[int] = None
    end_line: Optional[int] = None
    side: str = "head"
    qualname: str = ""


@dataclass
class Review:
    caption: str
    changed: List[Finding] = field(default_factory=list)
    hotspots: List[Finding] = field(default_factory=list)
    breaking: List[Finding] = field(default_factory=list)
    schema: List[Finding] = field(default_factory=list)
    coupling: List[str] = field(default_factory=list)
    untested: List[Finding] = field(default_factory=list)
    chips: Dict[str, List[str]] = field(default_factory=dict)
    dropped: Dict[str, int] = field(default_factory=dict)
    generated_files: int = 0

    @property
    def risks(self) -> List[Finding]:
        """Changed behavior. The old name was a top-five CRAP list."""
        return self.changed


def build_review(diff, base_sources: Dict[str, str], head_sources: Dict[str, str],
                 policy=None, coverage_map: Optional[Dict[str, float]] = None) -> Review:
    generated = strip_generated(diff, policy)
    measure_deltas(diff, base_sources, head_sources)
    _annotate_writers(diff, base_sources, head_sources)
    crap.annotate(diff, coverage_map or {})
    hunks = hunk_map(base_sources, head_sources)
    review = Review(caption=_caption(diff, base_sources, head_sources))
    review.generated_files = generated
    if generated:
        review.dropped["generated"] = generated
    review.breaking = _breaking(diff, hunks, review.dropped)
    review.changed, review.hotspots = _ranked(diff, hunks, review.dropped)
    review.schema = _schema(diff, hunks)
    review.coupling = _forbidden_coupling(diff)
    review.untested = _untested(diff, base_sources, head_sources, hunks)
    review.chips = _chips(diff, review)
    _cap_sections(review)
    return review


def dropped_line(review: Review) -> str:
    parts = []
    for key in ("generated", "whitespace", "same-file dependent", "pre-existing hotspot"):
        count = review.dropped.get(key, 0)
        if count:
            parts.append(f"{key} {count}")
    if not parts:
        return ""
    return "Dropped: " + ", ".join(parts)


def generated_line(review: Review) -> str:
    count = review.generated_files
    if not count:
        return ""
    word = "file" if count == 1 else "files"
    return f"generated clients regenerated, {count} {word}"


def ordered_texts(review: Review) -> List[str]:
    """The units a human and an agent both read, in the same order."""
    rows = [item.text for item in review.schema]
    rows.extend(item.text for item in review.untested)
    rows.extend(item.text for item in review.changed)
    rows.extend(item.text for item in review.hotspots)
    return rows


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


def _fan_in_by_file(diff) -> Dict[str, set]:
    """Importer files, excluding the file itself and generated code."""
    head: Dict[str, set] = {}
    base: Dict[str, set] = {}
    for imp in diff.imports:
        if is_generated(imp.source) or is_generated(imp.target):
            continue
        if imp.status in ("added", "unchanged") and imp.source != imp.target:
            head.setdefault(imp.target, set()).add(imp.source)
        if imp.status in ("removed", "unchanged") and imp.source != imp.target:
            base.setdefault(imp.target, set()).add(imp.source)
    counts = {}
    for path in set(head) | set(base):
        live = {src for src in (head.get(path) or set()) if src != path}
        old = {src for src in (base.get(path) or set()) if src != path}
        counts[path] = live if live else old
    return counts


def _self_importers(diff, path: str) -> bool:
    for imp in diff.imports:
        if imp.target == path and imp.source == path and imp.status in ("added", "unchanged", "removed"):
            return True
    return False


def _short_reason(reason: str) -> str:
    parts = []
    for part in reason.split(";"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("params "):
            parts.append("signature")
        elif part.startswith("return type "):
            parts.append("return type")
        elif part.startswith("modifiers "):
            parts.append("modifiers")
        else:
            parts.append(part)
    return "; ".join(parts)


def _span(unit) -> tuple:
    if unit is None:
        return None, None
    return getattr(unit, "line", None), getattr(unit, "end_line", None)


def _dependent_clause(path: str, fan_in: Dict[str, set]) -> str:
    count = len(fan_in.get(path) or ())
    if count <= 0:
        return ""
    word = "dependent" if count == 1 else "dependents"
    return f" \u00b7 {count} {word}"


def _file_of(qualname: str) -> str:
    return qualname.split("::", 1)[0]


def _finding(text: str, path: str, line, end_line, hunks, side: str = "head", qualname: str = "") -> Finding:
    cited_line, cited_end = cite(path, line, end_line, hunks)
    return Finding(text, path, cited_line, cited_end, side, qualname)


def _cap_sections(review: Review) -> None:
    review.changed = review.changed[:SECTION_CAP]
    review.hotspots = review.hotspots[:SECTION_CAP]
    review.breaking = review.breaking[:SECTION_CAP]
    review.schema = review.schema[:SECTION_CAP]
    review.untested = review.untested[:SECTION_CAP]


def _breaking(diff, hunks, dropped: Dict[str, int]) -> List[Finding]:
    fan_in = _fan_in_by_file(diff)
    ranked = []
    order = 0

    def add(path: str, text: str, unit=None, side: str = "head", qualname: str = "") -> None:
        nonlocal order
        external = fan_in.get(path) or set()
        if not external and _self_importers(diff, path):
            dropped["same-file dependent"] = dropped.get("same-file dependent", 0) + 1
            return
        line, end_line = _span(unit)
        ranked.append((
            len(external), order,
            _finding(text + _dependent_clause(path, fan_in), path, line, end_line, hunks, side, qualname),
        ))
        order += 1

    for type_change in diff.types:
        if not type_change.exported or is_generated(type_change.path):
            continue
        path = _file_of(type_change.qualname)
        if type_change.status == "removed":
            add(path, f"removed {type_change.kind} {type_change.qualname}", type_change, "base", type_change.qualname)
        elif type_change.added_relations or type_change.removed_relations or not _is_body_only(type_change.reason):
            if type_change.status == "modified":
                add(path, f"breaking {type_change.kind} {type_change.qualname}", type_change, qualname=type_change.qualname)
        for member in type_change.members:
            unit = member.after or member.before
            if unit is None or not unit.exported:
                continue
            side = "base" if member.status == "removed" else "head"
            qualname = f"{type_change.qualname}.{member.name}"
            if member.status == "removed":
                add(path, f"removed {qualname}", unit, side, qualname)
            elif member.status == "modified" and not _is_body_only(member.reason):
                why = _short_reason(member.reason)
                suffix = f": {why}" if why else ""
                add(path, f"breaking {qualname}{suffix}", member.after or unit, qualname=qualname)
    for fn in diff.functions:
        unit = fn.after or fn.before
        if unit is None or not unit.exported or is_generated(fn.path):
            continue
        path = _file_of(fn.qualname)
        if fn.status == "removed":
            add(path, f"removed {fn.qualname}", unit, "base", fn.qualname)
        elif fn.status == "modified" and not _is_body_only(fn.reason):
            why = _short_reason(fn.reason)
            suffix = f": {why}" if why else ""
            add(path, f"breaking {fn.qualname}{suffix}", fn.after or unit, qualname=fn.qualname)
    for table in diff.tables:
        if is_generated(table.path):
            continue
        if table.status == "removed":
            add(table.path, f"removed table {table.qualname}", qualname=table.qualname)
        for column in table.columns:
            if column.status == "removed":
                add(table.path, f"removed column {table.qualname}.{column.name}", qualname=f"{table.qualname}.{column.name}")
            elif column.status == "modified":
                add(table.path, f"breaking column {table.qualname}.{column.name}", qualname=f"{table.qualname}.{column.name}")
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, _, item in ranked]


def _unit_sort_key(change) -> tuple:
    return (getattr(change, "added_complexity", 0), getattr(change, "lines_added", 0))


def _ranked(diff, hunks, dropped: Dict[str, int]):
    changed = []
    hotspots = []

    def consider(change, qualname: str, path: str, unit) -> None:
        if is_generated(path):
            return
        if getattr(change, "whitespace", False):
            dropped["whitespace"] = dropped.get("whitespace", 0) + 1
            return
        line, end_line = _span(unit)
        if change.status == "added":
            text = f"{qualname} \u00b7 added complexity {change.added_complexity}"
            changed.append((_unit_sort_key(change), _finding(text, path, line, end_line, hunks, qualname=qualname)))
            return
        if change.status != "modified":
            return
        if is_small_hunk(change):
            size = change.lines_added + change.lines_removed
            text = f"pre-existing {qualname} \u00b7 hunk {size} lines"
            hotspots.append((size, _finding(text, path, line, end_line, hunks, qualname=qualname)))
            dropped["pre-existing hotspot"] = dropped.get("pre-existing hotspot", 0) + 1
            return
        if change.added_complexity > 0:
            text = f"{qualname} \u00b7 added complexity {change.added_complexity}"
            changed.append((_unit_sort_key(change), _finding(text, path, line, end_line, hunks, qualname=qualname)))
            return
        dropped["whitespace"] = dropped.get("whitespace", 0) + 1

    for type_change in diff.types:
        if type_change.status == "added" and not is_generated(type_change.path):
            changed.append((
                (0, 0),
                _finding(
                    f"{type_change.qualname} \u00b7 added complexity 0",
                    type_change.path, type_change.line, type_change.end_line, hunks,
                    qualname=type_change.qualname,
                ),
            ))
        for member in type_change.members:
            if member.status not in ("added", "modified"):
                continue
            unit = member.after or member.before
            consider(member, f"{type_change.qualname}.{member.name}", type_change.path, unit)
    for fn in diff.functions:
        if fn.status not in ("added", "modified"):
            continue
        consider(fn, fn.qualname, fn.path, fn.after or fn.before)

    changed.sort(key=lambda item: item[0], reverse=True)
    hotspots.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in changed], [item for _, item in hotspots]


def _schema(diff, hunks) -> List[Finding]:
    rows = []
    for table in diff.tables:
        if is_generated(table.path):
            continue
        if table.status == "removed":
            rows.append(_finding(
                f"removed table {table.name}", table.path, None, None, hunks, "base", table.qualname,
            ))
            continue
        if table.status == "added":
            rows.append(_finding(
                f"new table {table.name}{_writer_clause(table.columns)}",
                table.path, None, None, hunks, qualname=table.qualname,
            ))
            continue
        for column in table.columns:
            if column.status == "unchanged":
                continue
            qualname = f"{table.qualname}.{column.name}"
            if column.status == "added":
                text = f"new column {table.name}.{column.name}{_writer_clause([column])}"
            elif column.status == "removed":
                text = f"removed column {table.name}.{column.name}"
            else:
                text = f"column {table.name}.{column.name} {_short_type(column)}"
            rows.append(_finding(text, table.path, None, None, hunks, qualname=qualname))
    return rows


def _writer_clause(columns) -> str:
    new = []
    existing = []
    for column in columns:
        for area in getattr(column, "new_writer_areas", ()):
            if area not in new:
                new.append(area)
        for area in getattr(column, "existing_writer_areas", ()):
            if area not in existing:
                existing.append(area)
    if not new and not existing:
        return ""
    return (
        f" \u00b7 new writers: {', '.join(new) or 'none'}"
        f" \u00b7 existing writers: {', '.join(existing) or 'none'}"
    )


def _short_type(column) -> str:
    before = column.before or "\u2014"
    after = column.after or "\u2014"
    return f"{before} \u2192 {after}"


def _area(path: str) -> str:
    if "/" not in path:
        return path.rsplit(".", 1)[0]
    return path.split("/", 1)[0]


def _areas_mentioning(sources: Dict[str, str], needle: str) -> List[str]:
    if not needle:
        return []
    pattern = re.compile(rf"\b{re.escape(needle)}\b")
    areas = []
    for path in sorted(sources):
        if is_generated(path):
            continue
        text = sources.get(path) or ""
        if pattern.search(text) and _area(path) not in areas:
            areas.append(_area(path))
    return areas


def _union(*groups) -> List[str]:
    found = []
    for group in groups:
        for area in group:
            if area not in found:
                found.append(area)
    return found


def _annotate_writers(diff, base_sources: Dict[str, str], head_sources: Dict[str, str]) -> None:
    for table in diff.tables:
        existing_table = _areas_mentioning(base_sources, table.name)
        current_table = _areas_mentioning(head_sources, table.name)
        for column in table.columns:
            if column.status == "unchanged":
                continue
            existing_column = _areas_mentioning(base_sources, column.name)
            current_column = _areas_mentioning(head_sources, column.name)
            if table.status == "added":
                column.existing_writer_areas = []
                column.new_writer_areas = _union(current_table, current_column)
            elif column.status == "added":
                column.existing_writer_areas = existing_table
                column.new_writer_areas = [area for area in current_column if area not in existing_table]
            else:
                column.existing_writer_areas = existing_column
                column.new_writer_areas = [area for area in current_column if area not in existing_column]


def _forbidden_coupling(diff) -> List[str]:
    lines = []
    for violation in getattr(diff, "violations", []):
        if getattr(violation, "kind", "") != "illegal_edge" or not getattr(violation, "is_new", False):
            continue
        if is_generated(violation.source) or is_generated(violation.target):
            continue
        text = f"{violation.source} \u2192 {violation.target}"
        if text not in lines:
            lines.append(text)
    return lines or ["none"]


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return True
    return path.startswith(("tests/", "test/")) or "/tests/" in f"/{path}" or "/test/" in f"/{path}"


def _skip_type_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    lowered = stem.lower()
    return any(token in lowered for token in ("dto", "args", "payload", "enum"))


def _sibling_tests(path: str) -> List[str]:
    directory, name = path.rsplit("/", 1) if "/" in path else ("", path)
    stem, _, ext = name.rpartition(".")
    if not stem:
        return []

    def join(filename: str) -> str:
        return f"{directory}/{filename}" if directory else filename

    names = []
    if ext in ("ts", "tsx", "js", "jsx"):
        for suffix in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"):
            names.append(join(f"{stem}{suffix}"))
    if ext == "py":
        names.append(join(f"test_{stem}.py"))
        names.append(join(f"{stem}_test.py"))
        names.append(f"tests/test_{stem}.py")
        names.append(f"test/test_{stem}.py")
    return names


def _changed_paths(base_sources: Dict[str, str], head_sources: Dict[str, str]) -> List[str]:
    paths = set(base_sources) | set(head_sources)
    return sorted(path for path in paths if base_sources.get(path) != head_sources.get(path))


def _has_sibling_test(path: str, changed: set) -> bool:
    return any(candidate in changed for candidate in _sibling_tests(path))


def _untested(diff, base_sources: Dict[str, str], head_sources: Dict[str, str], hunks) -> List[Finding]:
    changed = set(_changed_paths(base_sources, head_sources))
    behavioral = []
    for path in sorted(changed):
        if _is_test_path(path) or is_generated(path) or _skip_type_file(path):
            continue
        if not path.endswith((".py", ".ts", ".tsx")):
            continue
        behavioral.append(path)
    tested = {path for path in behavioral if _has_sibling_test(path, changed)}
    rows = []
    for path in behavioral:
        if path in tested:
            continue
        line = min(hunks.get(path) or [1])
        rows.append(_finding(f"{path} has no sibling test", path, line, line, hunks, qualname=path))
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        for neighbor in behavioral:
            if neighbor == path or neighbor not in tested:
                continue
            neighbor_parent = neighbor.rsplit("/", 1)[0] if "/" in neighbor else ""
            if neighbor_parent != parent:
                continue
            note = f"{neighbor} has one"
            if note not in {row.text for row in rows}:
                rows.append(_finding(note, neighbor, None, None, hunks, qualname=neighbor))
    return rows


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
    for item in review.untested:
        if item.qualname:
            _add_chip(chips, item.qualname, "untested")
    return chips
