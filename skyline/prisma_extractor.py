"""Extract Prisma ``model`` blocks into the data-model view.

This is a syntax scan of ``*.prisma`` text, not a Prisma engine. SQL
migration files are a later increment and are not parsed here.
"""
from __future__ import annotations

import re

from .model import Column, ModuleModel, Table

_MODEL = re.compile(r"model\s+(\w+)\s*\{([^}]*)\}", re.MULTILINE)
_SCALARS = {
    "Int", "String", "Boolean", "DateTime", "Float", "Decimal", "Json", "Bytes", "BigInt",
}


def extract_prisma(path: str, source: str) -> ModuleModel:
    module = ModuleModel(path=path, language="prisma")
    for match in _MODEL.finditer(source):
        name = match.group(1)
        columns = {}
        relations = []
        for raw in match.group(2).splitlines():
            line = raw.strip()
            if not line or line.startswith("//") or line.startswith("@@") or line.startswith("@"):
                continue
            parts = line.split()
            if len(parts) < 2 or parts[0].startswith("@"):
                continue
            col_name, col_type = parts[0], parts[1]
            columns[col_name] = Column(name=col_name, type=col_type)
            base = col_type.rstrip("?").rstrip("[]").rstrip("?")
            if base not in _SCALARS and base[:1].isupper():
                relations.append(base)
        module.tables[name] = Table(
            name=name,
            qualname=f"{path}::{name}",
            path=path,
            columns=columns,
            relations=relations,
        )
    return module
