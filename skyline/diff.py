"""Compute a structural diff between two snapshots of a codebase (base ref
vs. head ref), at the type (class/interface) / member / function level.

Works identically regardless of which language extractor produced the
ModuleModel objects -- Python and TypeScript modules can even be diffed in
the same run, since both map onto the same generic dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .model import FunctionEntity, Member, ModuleModel, Relation
from .crap import CrapScore

Status = str  # "added" | "removed" | "modified" | "unchanged"

DASH = "\u2014"
ARROW = "\u2192"


@dataclass
class MemberChange:
    name: str
    status: Status
    before: Optional[Member] = None
    after: Optional[Member] = None
    reason: str = ""
    crap: Optional[CrapScore] = None


@dataclass
class TypeChange:
    name: str
    qualname: str
    path: str
    kind: str  # "class" | "interface"
    status: Status
    relations: List[Relation] = field(default_factory=list)  # current (head, or base if removed)
    added_relations: List[Relation] = field(default_factory=list)
    removed_relations: List[Relation] = field(default_factory=list)
    members: List[MemberChange] = field(default_factory=list)


@dataclass
class FunctionChange:
    name: str
    qualname: str
    path: str
    status: Status
    before: Optional[FunctionEntity] = None
    after: Optional[FunctionEntity] = None
    reason: str = ""
    crap: Optional[CrapScore] = None


@dataclass
class ModelDiff:
    types: List[TypeChange] = field(default_factory=list)
    functions: List[FunctionChange] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        c = {
            "types_added": 0, "types_removed": 0, "types_modified": 0,
            "functions_added": 0, "functions_removed": 0, "functions_modified": 0,
            "members_added": 0, "members_removed": 0, "members_modified": 0,
        }
        for t in self.types:
            if t.status in ("added", "removed", "modified"):
                c[f"types_{t.status}"] += 1
            for m in t.members:
                if m.status in ("added", "removed", "modified"):
                    c[f"members_{m.status}"] += 1
        for fn in self.functions:
            if fn.status in ("added", "removed", "modified"):
                c[f"functions_{fn.status}"] += 1
        return c


def _signature_changed_reason(before, after) -> str:
    reasons = []
    if before.params != after.params:
        reasons.append(f"params ({', '.join(before.params)}) {ARROW} ({', '.join(after.params)})")
    if before.modifiers != after.modifiers:
        b_mod = ', '.join(before.modifiers) or DASH
        a_mod = ', '.join(after.modifiers) or DASH
        reasons.append(f"modifiers ({b_mod}) {ARROW} ({a_mod})")
    if before.return_type != after.return_type:
        reasons.append(f"return type {before.return_type or DASH} {ARROW} {after.return_type or DASH}")
    if getattr(before, "optional", False) != getattr(after, "optional", False):
        reasons.append("optional changed")
    return "; ".join(reasons)


def _diff_members(before: Dict[str, Member], after: Dict[str, Member]) -> List[MemberChange]:
    changes: List[MemberChange] = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b is None:
            changes.append(MemberChange(name=name, status="added", after=a))
        elif a is None:
            changes.append(MemberChange(name=name, status="removed", before=b))
        else:
            reason = _signature_changed_reason(b, a)
            status = "modified" if reason else "unchanged"
            changes.append(MemberChange(name=name, status=status, before=b, after=a, reason=reason))
    return changes


def _diff_functions(before: Dict[str, FunctionEntity], after: Dict[str, FunctionEntity],
                     path: str) -> List[FunctionChange]:
    changes: List[FunctionChange] = []
    for name in sorted(set(before) | set(after)):
        bf, af = before.get(name), after.get(name)
        if bf is None:
            changes.append(FunctionChange(name=name, qualname=af.qualname, path=path, status="added", after=af))
        elif af is None:
            changes.append(FunctionChange(name=name, qualname=bf.qualname, path=path, status="removed", before=bf))
        else:
            reason = _signature_changed_reason(bf, af)
            changes.append(FunctionChange(
                name=name, qualname=af.qualname, path=path,
                status="modified" if reason else "unchanged", before=bf, after=af, reason=reason))
    return changes


def diff_models(base_modules: Dict[str, ModuleModel], head_modules: Dict[str, ModuleModel]) -> ModelDiff:
    diff = ModelDiff()
    all_paths = set(base_modules) | set(head_modules)

    for path in sorted(all_paths):
        b_mod = base_modules.get(path)
        h_mod = head_modules.get(path)
        b_types = b_mod.types if b_mod else {}
        h_types = h_mod.types if h_mod else {}
        b_funcs = b_mod.functions if b_mod else {}
        h_funcs = h_mod.functions if h_mod else {}

        for name in sorted(set(b_types) | set(h_types)):
            bt, ht = b_types.get(name), h_types.get(name)
            if bt is None:
                diff.types.append(TypeChange(
                    name=name, qualname=ht.qualname, path=path, kind=ht.kind, status="added",
                    relations=ht.relations, members=_diff_members({}, ht.members)))
            elif ht is None:
                diff.types.append(TypeChange(
                    name=name, qualname=bt.qualname, path=path, kind=bt.kind, status="removed",
                    relations=bt.relations, members=_diff_members(bt.members, {})))
            else:
                added_rel = [r for r in ht.relations if r not in bt.relations]
                removed_rel = [r for r in bt.relations if r not in ht.relations]
                member_changes = _diff_members(bt.members, ht.members)
                changed = bool(added_rel or removed_rel or
                               any(m.status != "unchanged" for m in member_changes))
                diff.types.append(TypeChange(
                    name=name, qualname=ht.qualname, path=path, kind=ht.kind,
                    status="modified" if changed else "unchanged",
                    relations=ht.relations, added_relations=added_rel, removed_relations=removed_rel,
                    members=member_changes))

        diff.functions.extend(_diff_functions(b_funcs, h_funcs, path))

    return diff
