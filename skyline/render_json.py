"""JSON render of the same diff the HTML report shows.

No new analysis. Missing a field that the HTML report shows is a bug here.
The risk list is every scored unit, not the HTML top-five summary.
"""
from __future__ import annotations

import json
from typing import Optional

from .diff import ModelDiff


def _crap(score) -> Optional[dict]:
    if score is None:
        return None
    return {
        "value": score.value,
        "band": score.band,
        "complexity": score.complexity,
        "coverage": score.coverage,
        "coverage_supplied": score.coverage_supplied,
        "label": score.label(),
    }


def _finding(item) -> dict:
    return {
        "text": item.text,
        "path": item.path,
        "line": item.line,
        "end_line": item.end_line,
        "side": item.side,
    }


def _full_risk(diff: ModelDiff) -> list:
    scored = []
    for type_change in diff.types:
        for member in type_change.members:
            if member.crap is None or member.status not in ("added", "modified"):
                continue
            unit = member.after or member.before
            scored.append((member.crap.value, {
                "name": f"{type_change.qualname}.{member.name}",
                "path": type_change.path,
                "line": getattr(unit, "line", None),
                "end_line": getattr(unit, "end_line", None),
                "crap": _crap(member.crap),
            }))
    for fn in diff.functions:
        if fn.crap is None or fn.status not in ("added", "modified"):
            continue
        unit = fn.after or fn.before
        scored.append((fn.crap.value, {
            "name": fn.qualname,
            "path": fn.path,
            "line": getattr(unit, "line", None),
            "end_line": getattr(unit, "end_line", None),
            "crap": _crap(fn.crap),
        }))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored]


def render_json(diff: ModelDiff, base_ref: str, head_ref: str, review=None) -> str:
    types = []
    for t in diff.types:
        if t.status == "unchanged":
            continue
        types.append({
            "name": t.name,
            "qualname": t.qualname,
            "path": t.path,
            "kind": t.kind,
            "status": t.status,
            "reason": t.reason,
            "line": t.line,
            "end_line": t.end_line,
            "added_relations": [{"target": n, "kind": k} for n, k in t.added_relations],
            "removed_relations": [{"target": n, "kind": k} for n, k in t.removed_relations],
            "members": [
                {
                    "name": m.name,
                    "status": m.status,
                    "reason": m.reason,
                    "crap": _crap(m.crap),
                    "line": getattr(m.after or m.before, "line", None),
                    "end_line": getattr(m.after or m.before, "end_line", None),
                }
                for m in t.members if m.status != "unchanged"
            ],
        })
    functions = []
    for fn in diff.functions:
        if fn.status == "unchanged":
            continue
        unit = fn.after or fn.before
        functions.append({
            "name": fn.name,
            "qualname": fn.qualname,
            "path": fn.path,
            "status": fn.status,
            "reason": fn.reason,
            "crap": _crap(fn.crap),
            "line": getattr(unit, "line", None),
            "end_line": getattr(unit, "end_line", None),
        })
    payload = {
        "base": base_ref,
        "head": head_ref,
        "stats": diff.counts(),
        "violations": [
            {"kind": v.kind, "message": v.message, "is_new": v.is_new}
            for v in getattr(diff, "violations", []) if getattr(v, "is_new", False)
        ],
        "types": types,
        "functions": functions,
        "breaking": [_finding(item) for item in (review.breaking if review else [])],
        "risk": _full_risk(diff),
        "coupling": list(review.coupling) if review else [],
        "untested": list(review.untested) if review else [],
        "data_model": [
            {
                "name": table.name,
                "qualname": table.qualname,
                "path": table.path,
                "status": table.status,
                "relations": list(table.relations),
                "columns": [
                    {"name": col.name, "status": col.status, "before": col.before, "after": col.after}
                    for col in table.columns if col.status != "unchanged"
                ],
            }
            for table in diff.tables if table.status != "unchanged" or any(
                col.status != "unchanged" for col in table.columns
            )
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
