"""Versioned JSON for an as-built map.

``model.json`` is generated. Regenerating it from source must be lossless.
Do not hand-edit it; code plus policy are the source of truth.
"""
from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from .model import FunctionEntity, Member, ModuleModel, TypeEntity

MODEL_VERSION = 1


def dump_modules(modules: Dict[str, ModuleModel], ref: Optional[str] = None,
                 sha: Optional[str] = None) -> str:
    payload = {
        "version": MODEL_VERSION,
        "ref": ref,
        "sha": sha,
        "modules": {path: _module_to_dict(mod) for path, mod in sorted(modules.items())},
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_modules(raw: str) -> Tuple[Optional[str], Optional[str], Dict[str, ModuleModel]]:
    data = json.loads(raw)
    version = data.get("version")
    if version != MODEL_VERSION:
        raise ValueError(f"unsupported skyline model version: {version}")
    modules = {path: _module_from_dict(item) for path, item in data.get("modules", {}).items()}
    return data.get("ref"), data.get("sha"), modules


def _module_to_dict(mod: ModuleModel) -> dict:
    return {
        "path": mod.path,
        "language": mod.language,
        "imports": list(mod.imports),
        "types": {name: _type_to_dict(t) for name, t in mod.types.items()},
        "functions": {name: _function_to_dict(fn) for name, fn in mod.functions.items()},
        "tables": {name: _table_to_dict(table) for name, table in getattr(mod, "tables", {}).items()},
    }


def _type_to_dict(t: TypeEntity) -> dict:
    return {
        "name": t.name,
        "qualname": t.qualname,
        "kind": t.kind,
        "decorators": list(t.decorators),
        "relations": [list(r) for r in t.relations],
        "exported": t.exported,
        "members": {name: _member_to_dict(m) for name, m in t.members.items()},
    }


def _member_to_dict(m: Member) -> dict:
    return {
        "name": m.name,
        "kind": m.kind,
        "params": list(m.params),
        "modifiers": list(m.modifiers),
        "return_type": m.return_type,
        "optional": m.optional,
        "complexity": m.complexity,
        "body_hash": m.body_hash,
        "exported": m.exported,
    }


def _function_to_dict(fn: FunctionEntity) -> dict:
    return {
        "name": fn.name,
        "qualname": fn.qualname,
        "params": list(fn.params),
        "modifiers": list(fn.modifiers),
        "return_type": fn.return_type,
        "exported": fn.exported,
        "complexity": fn.complexity,
        "body_hash": fn.body_hash,
    }


def _table_to_dict(table) -> dict:
    return {
        "name": table.name,
        "qualname": table.qualname,
        "path": table.path,
        "columns": {
            name: {"name": col.name, "type": col.type}
            for name, col in table.columns.items()
        },
        "relations": list(table.relations),
    }


def _module_from_dict(data: dict) -> ModuleModel:
    module = ModuleModel(
        path=data["path"],
        language=data.get("language", "python"),
        imports=list(data.get("imports") or []),
    )
    for name, item in (data.get("types") or {}).items():
        module.types[name] = _type_from_dict(item)
    for name, item in (data.get("functions") or {}).items():
        module.functions[name] = _function_from_dict(item)
    tables = getattr(module, "tables", None)
    if tables is not None:
        for name, item in (data.get("tables") or {}).items():
            tables[name] = _table_from_dict(item)
    return module


def _type_from_dict(data: dict) -> TypeEntity:
    return TypeEntity(
        name=data["name"],
        qualname=data["qualname"],
        kind=data.get("kind", "class"),
        decorators=list(data.get("decorators") or []),
        relations=[tuple(r) for r in data.get("relations") or []],
        members={name: _member_from_dict(m) for name, m in (data.get("members") or {}).items()},
        exported=data.get("exported", True),
    )


def _member_from_dict(data: dict) -> Member:
    return Member(
        name=data["name"],
        kind=data.get("kind", "method"),
        params=list(data.get("params") or []),
        modifiers=list(data.get("modifiers") or []),
        return_type=data.get("return_type"),
        optional=data.get("optional", False),
        complexity=data.get("complexity"),
        body_hash=data.get("body_hash"),
        exported=data.get("exported", True),
    )


def _function_from_dict(data: dict) -> FunctionEntity:
    return FunctionEntity(
        name=data["name"],
        qualname=data["qualname"],
        params=list(data.get("params") or []),
        modifiers=list(data.get("modifiers") or []),
        return_type=data.get("return_type"),
        exported=data.get("exported", True),
        complexity=data.get("complexity"),
        body_hash=data.get("body_hash"),
    )


def _table_from_dict(data: dict):
    from .model import Column, Table

    return Table(
        name=data["name"],
        qualname=data["qualname"],
        path=data["path"],
        columns={
            name: Column(name=col["name"], type=col.get("type"))
            for name, col in (data.get("columns") or {}).items()
        },
        relations=list(data.get("relations") or []),
    )
