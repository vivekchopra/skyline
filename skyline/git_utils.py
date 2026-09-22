"""Thin wrappers around the ``git`` CLI for reading source files at two refs.

No GitPython dependency: PRs are almost always reviewed on a machine that
already has git installed, and shelling out keeps this package
dependency-free.
"""
from __future__ import annotations

import subprocess
from typing import Dict, List, Sequence


def _run(repo: str, args: List[str]) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def changed_source_files(repo: str, base: str, head: str, extensions: Sequence[str]) -> List[str]:
    """Paths of files (matching any of `extensions`, e.g. (".py", ".ts")) that
    differ between base and head (three-dot diff, i.e. relative to their
    merge-base -- the same range GitHub shows for a pull request).
    """
    pathspecs = [f"*{ext}" for ext in extensions]
    out = _run(repo, ["diff", "--name-only", f"{base}...{head}", "--", *pathspecs])
    return [line.strip() for line in out.splitlines() if line.strip()]


def list_files_at_ref(repo: str, ref: str, paths: List[str]) -> Dict[str, str]:
    """{path: source} for each path that exists at ref.

    Paths added in head (missing at base) or removed in head (missing at
    head) are simply absent from the returned dict, which the diff layer
    treats as "everything in this file is new/removed".
    """
    out: Dict[str, str] = {}
    for path in paths:
        try:
            out[path] = _run(repo, ["show", f"{ref}:{path}"])
        except RuntimeError:
            continue
    return out
