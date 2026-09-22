"""Python-side wrapper around the bundled Node.js TypeScript extractor.

The actual parsing is done by ``ts_extractor/extract.js`` using the real
TypeScript compiler API (so generics, decorators, JSX, overloads, etc. are
handled correctly instead of guessed at with regex). This module's job is
just to get that script + a `typescript` install available, feed it source,
and translate its JSON output into the shared dataclasses in model.py.

The TypeScript compiler itself (~25 MB via npm) is *not* bundled in the
pip package; it's installed once, lazily, into a per-user cache directory
the first time TypeScript files are analyzed. This keeps `pip install
skyline` itself dependency-free for Python-only users.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict

from .model import FunctionEntity, Member, ModuleModel, TypeEntity

_BUNDLED_DIR = Path(__file__).parent / "ts_extractor"
_CACHE_DIR = Path.home() / ".cache" / "skyline" / "ts_extractor"


class ToolingError(RuntimeError):
    """Raised when Node.js/npm/TypeScript aren't available or fail."""


def _ensure_tooling() -> Path:
    if shutil.which("node") is None:
        raise ToolingError(
            "TypeScript support needs Node.js (18+) on PATH to run the bundled "
            "TypeScript-compiler-based extractor. Install Node.js and try again."
        )

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("extract.js", "package.json"):
        shutil.copyfile(_BUNDLED_DIR / name, _CACHE_DIR / name)

    if not (_CACHE_DIR / "node_modules" / "typescript").exists():
        if shutil.which("npm") is None:
            raise ToolingError(
                "TypeScript support needs npm on PATH to install the TypeScript "
                f"compiler once into {_CACHE_DIR}. npm was not found."
            )
        print(
            f"skyline: installing the TypeScript compiler into {_CACHE_DIR} "
            "(first run only)...",
            file=sys.stderr,
        )
        result = subprocess.run(
            ["npm", "install", "--no-audit", "--no-fund", "--omit=dev"],
            cwd=_CACHE_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ToolingError(f"npm install failed:\n{result.stderr}")
    return _CACHE_DIR


def _to_member(data: dict) -> Member:
    return Member(
        name=data["name"],
        kind=data["kind"],
        params=data.get("params", []),
        modifiers=data.get("modifiers", []),
        return_type=data.get("return_type"),
        optional=data.get("optional", False),
        complexity=data.get("complexity"),
    )


def _to_module(data: dict) -> ModuleModel:
    path = data["path"]
    module = ModuleModel(path=path, language="typescript")
    for name, t in data.get("types", {}).items():
        module.types[name] = TypeEntity(
            name=t["name"],
            qualname=f"{path}::{t['name']}",
            kind=t["kind"],
            decorators=t.get("decorators", []),
            relations=[tuple(r) for r in t.get("relations", [])],
            members={mn: _to_member(m) for mn, m in t.get("members", {}).items()},
            exported=t.get("exported", True),
        )
    for name, fn in data.get("functions", {}).items():
        module.functions[name] = FunctionEntity(
            name=fn["name"],
            qualname=f"{path}::{fn['name']}",
            params=fn.get("params", []),
            modifiers=fn.get("modifiers", []),
            return_type=fn.get("return_type"),
            exported=fn.get("exported", True),
            complexity=fn.get("complexity"),
        )
    return module


def extract_modules(files: Dict[str, str]) -> Dict[str, ModuleModel]:
    """files: {path: source} for .ts/.tsx files. Returns {path: ModuleModel}."""
    if not files:
        return {}
    tooling_dir = _ensure_tooling()
    payload = json.dumps([{"path": p, "source": s} for p, s in files.items()])
    result = subprocess.run(
        ["node", str(tooling_dir / "extract.js")],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tooling_dir,
    )
    if result.returncode != 0:
        raise ToolingError(f"TypeScript extraction failed:\n{result.stderr}")
    data = json.loads(result.stdout)
    return {item["path"]: _to_module(item) for item in data}
