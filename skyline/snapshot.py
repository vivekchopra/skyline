"""Write and load an as-built map for one git ref.

The examined repo's owner chooses whether ``.skyline/`` is gitignored or
checked in. Skyline does not write that choice for them. Checking the
files in is a lockfile; ignoring them is fine when CI always regenerates.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .git_utils import list_files_at_ref, list_tracked_source_files, rev_parse
from .languages import build_modules
from .model import ModuleModel
from .serialize import dump_modules, load_modules


def snapshot_dir(repo: str, out_dir: str) -> Path:
    path = Path(out_dir)
    if not path.is_absolute():
        path = Path(repo) / path
    return path


def extract_ref(repo: str, ref: str, extensions) -> Dict[str, ModuleModel]:
    paths = list_tracked_source_files(repo, ref, extensions)
    files = list_files_at_ref(repo, ref, paths)
    return build_modules(files)


def write_snapshot(repo: str, ref: str, extensions, out_dir: str, render: bool = False) -> Path:
    directory = snapshot_dir(repo, out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    sha = rev_parse(repo, ref)
    modules = extract_ref(repo, ref, extensions)
    model_path = directory / "model.json"
    model_path.write_text(dump_modules(modules, ref=ref, sha=sha), encoding="utf-8")
    if render:
        from .diff import diff_models
        from .render_mermaid import modules_mermaid
        from .render_svg import build_diagram_svg

        (directory / "map.md").write_text(modules_mermaid(modules) + "\n", encoding="utf-8")
        (directory / "map.svg").write_text(
            build_diagram_svg(diff_models({}, modules)), encoding="utf-8"
        )
    return model_path


def load_fresh_snapshot(repo: str, ref: str, out_dir: str) -> Optional[Dict[str, ModuleModel]]:
    """Load ``model.json`` when it was generated for this ref. Otherwise None."""
    model_path = snapshot_dir(repo, out_dir) / "model.json"
    if not model_path.is_file():
        return None
    try:
        stored_ref, stored_sha, modules = load_modules(model_path.read_text(encoding="utf-8"))
        sha = rev_parse(repo, ref)
    except (OSError, ValueError, RuntimeError):
        return None
    if stored_sha == sha or stored_ref == ref:
        return modules
    return None
