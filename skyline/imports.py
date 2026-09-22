"""Resolve import specifiers to files that were actually extracted.

Unresolved third-party modules are dropped. They are not architecture edges.
"""
from __future__ import annotations

from typing import Optional, Set


def resolve_import(importer: str, spec: str, files: Set[str], language: str) -> Optional[str]:
    if not spec:
        return None
    if language == "python":
        return _resolve_python(importer, spec, files)
    return _resolve_typescript(importer, spec, files)


def _first_existing(candidates, files: Set[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def _resolve_python(importer: str, spec: str, files: Set[str]) -> Optional[str]:
    if spec.startswith("."):
        level = len(spec) - len(spec.lstrip("."))
        mod = spec[level:]
        base = importer.split("/")[:-1]
        up = level - 1
        if up:
            if up > len(base):
                return None
            base = base[:-up]
        if mod:
            base = base + mod.split(".")
        rel = "/".join(part for part in base if part)
    else:
        rel = spec.replace(".", "/")
    if not rel:
        return None
    return _first_existing((f"{rel}.py", f"{rel}/__init__.py"), files)


def _resolve_typescript(importer: str, spec: str, files: Set[str]) -> Optional[str]:
    # Bare specifiers (``react``, ``@scope/pkg``) are third-party.
    if not spec.startswith("."):
        return None
    parts = importer.split("/")[:-1]
    for part in spec.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        for ext in (".ts", ".tsx", ".js", ".jsx"):
            if part.endswith(ext):
                part = part[: -len(ext)]
                break
        parts.append(part)
    rel = "/".join(parts)
    if not rel:
        return None
    return _first_existing(
        (rel, f"{rel}.ts", f"{rel}.tsx", f"{rel}.js", f"{rel}/index.ts", f"{rel}/index.tsx"),
        files,
    )
