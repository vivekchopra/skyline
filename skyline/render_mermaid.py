"""Lossy Mermaid diagrams for a snapshot or a PR overlay.

Mermaid cannot carry qualnames, CRAP, or policy color. The HTML report
remains the full picture. These diagrams are for the PR comment and for
an optional snapshot render.
"""
from __future__ import annotations

from typing import Dict

from .diff import ModelDiff
from .model import ModuleModel


def _id(qualname: str) -> str:
    cleaned = []
    for ch in qualname:
        cleaned.append(ch if ch.isalnum() else "_")
    ident = "".join(cleaned).strip("_")
    return ident or "unit"


def modules_mermaid(modules: Dict[str, ModuleModel]) -> str:
    lines = ["classDiagram"]
    names = {}
    for path, mod in sorted(modules.items()):
        for type_entity in mod.types.values():
            ident = _id(type_entity.qualname)
            names[(path, type_entity.name)] = ident
            lines.append(f"  class {ident}")
    for path, mod in sorted(modules.items()):
        for type_entity in mod.types.values():
            src = names[(path, type_entity.name)]
            for target, kind in type_entity.relations:
                dst = names.get((path, target))
                if dst is None:
                    dst = _id(f"external::{target}")
                    lines.append(f"  class {dst}")
                    names[(path, target)] = dst
                if kind == "implements":
                    lines.append(f"  {dst} <|.. {src}")
                else:
                    lines.append(f"  {dst} <|-- {src}")
    if len(lines) == 1:
        lines.append("  class NoTypes")
    return "\n".join(lines)


def diff_class_mermaid(diff: ModelDiff) -> str:
    lines = ["classDiagram"]
    drawn = [t for t in diff.types if t.status in ("added", "removed", "modified")]
    ids = {t.qualname: _id(t.qualname) for t in drawn}
    for t in drawn:
        stereotype = "" if t.kind == "class" else f"«{t.kind}» "
        lines.append(f"  class {ids[t.qualname]}[\"{stereotype}{t.name}\"]")
        for member in t.members:
            if member.status == "unchanged":
                continue
            lines.append(f"  {ids[t.qualname]} : {member.status} {member.name}")
    for t in drawn:
        for target, kind in t.relations:
            dst = _id(f"{t.path}::{target}")
            if dst not in ids.values():
                lines.append(f"  class {dst}[\"{target}\"]")
            arrow = "<|.." if kind == "implements" else "<|--"
            lines.append(f"  {dst} {arrow} {ids[t.qualname]}")
    changed_fns = [fn for fn in diff.functions if fn.status in ("added", "removed", "modified")]
    for fn in changed_fns:
        ident = _id(fn.qualname + "_fn")
        lines.append(f"  class {ident}[\"«function» {fn.name}\"]")
    if len(lines) == 1:
        lines.append("  class NoChanges")
    return "\n".join(lines)


def data_mermaid(diff: ModelDiff) -> str:
    tables = [t for t in diff.tables if t.status in ("added", "removed", "modified")]
    if not tables:
        return ""
    lines = ["erDiagram"]
    for table in tables:
        ident = _id(table.qualname)
        lines.append(f"  {ident} {{")
        shown = [col for col in table.columns if col.status != "unchanged"]
        if not shown:
            lines.append("    string id")
        for col in shown:
            col_type = (col.after or col.before or "string").split(".")[-1]
            safe_type = "".join(ch if ch.isalnum() else "_" for ch in col_type) or "string"
            lines.append(f"    {safe_type} {col.name}")
        lines.append("  }")
    return "\n".join(lines)


def coupling_mermaid(diff: ModelDiff) -> str:
    lines = ["flowchart LR"]
    edges = [i for i in diff.imports if i.status in ("added", "removed")]
    if not edges:
        lines.append("  empty[\"No import changes\"]")
        return "\n".join(lines)
    for imp in edges:
        src = _id(imp.source)
        dst = _id(imp.target)
        label = "added" if imp.status == "added" else "removed"
        lines.append(f"  {src}[\"{imp.source}\"] -->|{label}| {dst}[\"{imp.target}\"]")
    return "\n".join(lines)
