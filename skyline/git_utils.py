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


def resolve_ref(repo: str, ref: str) -> str:
    """Return a revision Git can resolve for ``ref``.

    Fetch stores a remote branch as ``refs/remotes/<remote>/<branch>`` and
    does not create a local branch. When ``ref`` is missing locally and
    exactly one remote has that branch, return ``<remote>/<branch>``.
    """
    if _ref_resolves(repo, ref):
        return ref
    matches = _remote_tracking_matches(repo, ref)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        listed = ", ".join(matches)
        raise RuntimeError(
            f"git ref {ref!r} matches more than one remote-tracking branch: {listed}. "
            f"Pass one of those names."
        )
    raise RuntimeError(
        f"git ref {ref!r} was not found. "
        f"Fetch the branch, or pass a remote-tracking name such as origin/{ref}."
    )


def _ref_resolves(repo: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _remote_tracking_matches(repo: str, ref: str) -> List[str]:
    remotes = [line.strip() for line in _run(repo, ["remote"]).splitlines() if line.strip()]
    matches = []
    for remote in remotes:
        candidate = f"{remote}/{ref}"
        if _ref_resolves(repo, f"refs/remotes/{candidate}"):
            matches.append(candidate)
    return matches


def changed_source_files(repo: str, base: str, head: str, extensions: Sequence[str]) -> List[str]:
    """Paths of files (matching any of `extensions`, e.g. (".py", ".ts")) that
    differ between base and head (three-dot diff, i.e. relative to their
    merge-base -- the same range GitHub shows for a pull request).
    """
    pathspecs = [f"*{ext}" for ext in extensions]
    out = _run(repo, ["diff", "--name-only", f"{base}...{head}", "--", *pathspecs])
    return [line.strip() for line in out.splitlines() if line.strip()]


def rev_parse(repo: str, ref: str) -> str:
    return _run(repo, ["rev-parse", ref]).strip()


def list_tracked_source_files(repo: str, ref: str, extensions: Sequence[str]) -> List[str]:
    """Source files tracked at ``ref``.

    ``git ls-tree`` lists the committed tree, so gitignored files that were
    never added are absent. That is the gitignore-aware file set at a ref.
    """
    out = _run(repo, ["ls-tree", "-r", "--name-only", ref])
    paths = []
    for line in out.splitlines():
        path = line.strip()
        if path and any(path.endswith(ext) for ext in extensions):
            paths.append(path)
    return paths


def list_files_at_ref(repo: str, ref: str, paths: List[str], on_file=None) -> Dict[str, str]:
    """{path: source} for each path that exists at ref.

    Paths added in head (missing at base) or removed in head (missing at
    head) are simply absent from the returned dict, which the diff layer
    treats as "everything in this file is new/removed".

    ``on_file(index, total)`` is called after each path, 1-based, so a
    caller can show progress without printing a line per file.
    """
    out: Dict[str, str] = {}
    total = len(paths)
    for index, path in enumerate(paths, start=1):
        try:
            out[path] = _run(repo, ["show", f"{ref}:{path}"])
        except RuntimeError:
            pass
        if on_file is not None:
            on_file(index, total)
    return out
