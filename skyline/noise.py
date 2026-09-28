"""Generated files are not a review. Drop them before scoring or drawing."""
from __future__ import annotations

from fnmatch import fnmatch
from typing import List, Optional, Sequence

# Basename matches, plus anything under a __generated__ directory.
_BASENAMES = {"graphql.ts", "types.ts", "dom-contract.txt"}


def is_generated(path: str, extra: Sequence[str] = ()) -> bool:
    norm = path.replace("\\", "/").lstrip("./")
    if not norm:
        return False
    parts = norm.split("/")
    if "__generated__" in parts:
        return True
    if parts[-1] in _BASENAMES:
        return True
    for pattern in extra:
        if _match(pattern, norm):
            return True
    return False


def _match(pattern: str, path: str) -> bool:
    pattern = pattern.replace("\\", "/").lstrip("./")
    if pattern.startswith("**/") and pattern.endswith("/**"):
        return pattern[3:-3] in path.split("/")
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return path == tail or path.endswith("/" + tail) or path.split("/")[-1] == tail
    return fnmatch(path, pattern)


def strip_generated(diff, policy=None) -> int:
    """Remove generated paths from a diff. Return how many changed files went away.

    Idempotent. The diagram, the scores, and the review then see hand-written code.
    """
    if getattr(diff, "_generated_stripped", False):
        return int(getattr(diff, "generated_count", 0))
    extra: List[str] = list(getattr(policy, "generated", ()) or ())
    changed = set()

    def generated(path: str) -> bool:
        return bool(path) and is_generated(path, extra)

    types = []
    for type_change in diff.types:
        if generated(type_change.path):
            if type_change.status != "unchanged" or any(m.status != "unchanged" for m in type_change.members):
                changed.add(type_change.path)
            continue
        types.append(type_change)
    diff.types = types

    functions = []
    for fn in diff.functions:
        if generated(fn.path):
            if fn.status != "unchanged":
                changed.add(fn.path)
            continue
        functions.append(fn)
    diff.functions = functions

    imports = []
    for imp in diff.imports:
        if generated(imp.source) or generated(imp.target):
            if imp.status != "unchanged":
                if generated(imp.source):
                    changed.add(imp.source)
                if generated(imp.target):
                    changed.add(imp.target)
            continue
        imports.append(imp)
    diff.imports = imports

    tables = []
    for table in diff.tables:
        if generated(table.path):
            if table.status != "unchanged" or any(col.status != "unchanged" for col in table.columns):
                changed.add(table.path)
            continue
        tables.append(table)
    diff.tables = tables

    diff.generated_count = len(changed)
    diff._generated_stripped = True
    return len(changed)
