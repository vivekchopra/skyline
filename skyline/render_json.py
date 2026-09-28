"""JSON render of the same review the HTML report and the comment show.

No new analysis. The ranked lists are the review's lists, capped, not every
scored unit in the tree.
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
    row = {
        "text": item.text,
        "path": item.path,
        "qualname": getattr(item, "qualname", ""),
        "line": item.line,
        "end_line": item.end_line,
        "side": item.side,
    }
    return row


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
        "changed_behavior": [_finding(item) for item in (review.changed if review else [])],
        "hotspots": [_finding(item) for item in (review.hotspots if review else [])],
        "schema": [_finding(item) for item in (review.schema if review else [])],
        "coupling": list(review.coupling) if review else ["none"],
        "untested": [_finding(item) for item in (review.untested if review else [])],
        "dropped": dict(review.dropped) if review else {},
        "generated_files": review.generated_files if review else 0,
        "data_model": [
            {
                "name": table.name,
                "qualname": table.qualname,
                "path": table.path,
                "status": table.status,
                "relations": list(table.relations),
                "columns": [
                    {
                        "name": col.name,
                        "status": col.status,
                        "before": col.before,
                        "after": col.after,
                        "new_writer_areas": list(getattr(col, "new_writer_areas", ())),
                        "existing_writer_areas": list(getattr(col, "existing_writer_areas", ())),
                    }
                    for col in table.columns if col.status != "unchanged"
                ],
            }
            for table in diff.tables if table.status != "unchanged" or any(
                col.status != "unchanged" for col in table.columns
            )
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
