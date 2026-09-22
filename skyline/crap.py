"""CRAP (Change Risk Anti-Patterns) scoring.

    CRAP = complexity^2 * (1 - coverage)^3 + complexity

This is a per-method/function risk score combining cyclomatic complexity
with test coverage: a complex, untested method scores far worse than an
equally complex, well-tested one. The formula is Alberto Savoia's, from
the original CRAP4J tool.

**This feature -- and the general idea of overlaying a risk score directly
on a structural diagram -- was inspired by Robert C. Martin's
(unclebob's) uml-viewer and crap4clj:**

  https://github.com/unclebob/uml-viewer
  https://github.com/unclebob/crap4clj

uml-viewer overlays CRAP and mutation-testing scores onto a live UML
diagram for a Clojure codebase, painting boxes red-to-green by risk. This
module borrows both the formula and its most opinionated design choice:
**missing coverage data counts as 0% (the worst case), not "unknown."**
The reasoning, straight from uml-viewer's README, is that an untested
function should never look safer than a tested one just because the tool
wasn't told about it. skyline is not affiliated with those projects;
they're Clojure-specific and considerably more sophisticated (they also
integrate mutation testing) -- if that's what you need, use them directly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .diff import ModelDiff

# (upper bound inclusive, band name, color) -- ordered ascending.
# Thresholds follow CRAP4J's original published guidance (a CRAP score
# over 30 is considered high-risk and worth attention); the low/moderate
# split is skyline's own, chosen to still surface "worth a second look"
# methods without the whole report turning red.
_BANDS = (
    (5.0, "low", "#2e7d32"),
    (10.0, "moderate", "#f9a825"),
    (30.0, "high", "#e65100"),
    (float("inf"), "severe", "#c62828"),
)


@dataclass
class CrapScore:
    complexity: int
    coverage: float  # 0..1, the value actually used (0.0 if not supplied)
    coverage_supplied: bool
    value: float
    band: str  # "low" | "moderate" | "high" | "severe"
    color: str

    def label(self) -> str:
        return f"CRAP {self.value:g}"


def score(complexity: Optional[int], coverage: Optional[float]) -> Optional[CrapScore]:
    """None if complexity is unknown (e.g. an interface method with no body).
    coverage=None is treated as 0% -- see module docstring."""
    if complexity is None:
        return None
    supplied = coverage is not None
    cov = 0.0 if coverage is None else max(0.0, min(1.0, coverage))
    crap = complexity ** 2 * (1 - cov) ** 3 + complexity
    for threshold, band, color in _BANDS:
        if crap <= threshold:
            return CrapScore(complexity=complexity, coverage=cov, coverage_supplied=supplied,
                              value=round(crap, 1), band=band, color=color)
    return CrapScore(complexity=complexity, coverage=cov, coverage_supplied=supplied,
                      value=round(crap, 1), band="severe", color="#c62828")  # unreachable


def load_coverage_map(path: Optional[str]) -> Dict[str, float]:
    """Load an optional coverage map: a JSON object of
    {"path::Type.member": 0.83, "path::function_name": 0.5, ...} -> a
    fraction 0..1. Keys use the same qualname format skyline uses
    internally (see README: 'Coverage input'). Entries not present in the
    map are treated as 0% coverage, not "unknown" -- see module docstring.
    """
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {str(k): float(v) for k, v in data.items()}


def annotate(diff: "ModelDiff", coverage_map: Dict[str, float]) -> None:
    """Attach a CrapScore to every added/modified member and function in
    `diff`, in place. Only added/modified entries are scored -- a removed
    method's risk no longer matters, and an unchanged one wasn't touched by
    this PR, so it's not part of what needs reviewing right now.
    """
    for t in diff.types:
        for m in t.members:
            if m.status not in ("added", "modified") or m.after is None:
                continue
            key = f"{t.qualname}.{m.name}"
            m.crap = score(m.after.complexity, coverage_map.get(key))
    for fn in diff.functions:
        if fn.status not in ("added", "modified") or fn.after is None:
            continue
        fn.crap = score(fn.after.complexity, coverage_map.get(fn.qualname))
