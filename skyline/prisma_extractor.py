"""Extract Prisma ``model`` blocks into the data-model view.

This is a syntax scan of ``*.prisma`` text, not a Prisma engine. SQL
migration files are a later increment and are not parsed here.

A model body may contain ``}`` inside a string. The first closing brace
is not the end of the model.
"""
from __future__ import annotations

import re

from .model import Column, ModuleModel, Table

_MODEL_START = re.compile(r"\bmodel\s+(\w+)\s*\{")
_SCALARS = {
    "Int", "String", "Boolean", "DateTime", "Float", "Decimal", "Json", "Bytes", "BigInt",
}


def extract_prisma(path: str, source: str) -> ModuleModel:
    module = ModuleModel(path=path, language="prisma")
    for name, body in _model_bodies(source):
        columns = {}
        relations = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("//") or line.startswith("@@") or line.startswith("@"):
                continue
            parts = line.split()
            if len(parts) < 2 or parts[0].startswith("@"):
                continue
            col_name, col_type = parts[0], _norm_type(parts[1])
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


def _norm_type(value: str) -> str:
    return " ".join(value.split())


def _model_bodies(source: str):
    cursor = 0
    while True:
        match = _MODEL_START.search(source, cursor)
        if match is None:
            return
        body, cursor = _balanced_body(source, match.end() - 1)
        yield match.group(1), body


def _balanced_body(source: str, brace_at: int):
    """Return the text inside the brace at ``brace_at``, and the index after it."""
    depth = 0
    index = brace_at
    start = brace_at + 1
    quote = None
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            index += 1
            continue
        if char == "/" and index + 1 < len(source) and source[index + 1] == "/":
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index], index + 1
        index += 1
    return source[start:], len(source)
