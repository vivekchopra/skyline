"""Routes changed files to the right per-language extractor, by extension,
and merges the results into one {path: ModuleModel} dict. A single `diff`
run can freely mix Python and TypeScript files -- the diff/render layers
don't care which language a ModuleModel came from.
"""
from __future__ import annotations

from typing import Dict, List

from .model import ModuleModel

PYTHON_EXTENSIONS = (".py",)
TYPESCRIPT_EXTENSIONS = (".ts", ".tsx")
PRISMA_EXTENSIONS = (".prisma",)
ALL_EXTENSIONS = PYTHON_EXTENSIONS + TYPESCRIPT_EXTENSIONS + PRISMA_EXTENSIONS


def build_modules(files: Dict[str, str], on_file=None) -> Dict[str, ModuleModel]:
    """files: {path: source}, any mix of extensions in ALL_EXTENSIONS.

    ``on_file(done, total)`` fires as each file is parsed. TypeScript is
    one compiler run, so it reports once for the whole batch.
    """
    py_files = {p: s for p, s in files.items() if p.endswith(PYTHON_EXTENSIONS)}
    ts_files = {p: s for p, s in files.items() if p.endswith(TYPESCRIPT_EXTENSIONS)}
    prisma_files = {p: s for p, s in files.items() if p.endswith(PRISMA_EXTENSIONS)}
    total = len(py_files) + (1 if ts_files else 0) + len(prisma_files)
    done = 0

    def tick() -> None:
        nonlocal done
        done += 1
        if on_file is not None:
            on_file(done, total)

    modules: Dict[str, ModuleModel] = {}

    if py_files:
        from .python_extractor import extract_module
        for path, source in py_files.items():
            modules[path] = extract_module(path, source)
            tick()

    if ts_files:
        from .ts_client import extract_modules
        modules.update(extract_modules(ts_files))
        tick()

    if prisma_files:
        from .prisma_extractor import extract_prisma
        for path, source in prisma_files.items():
            modules[path] = extract_prisma(path, source)
            tick()

    return modules


def extensions_for(langs: List[str]) -> tuple:
    exts = []
    if "python" in langs:
        exts.extend(PYTHON_EXTENSIONS)
    if "typescript" in langs:
        exts.extend(TYPESCRIPT_EXTENSIONS)
    exts.extend(PRISMA_EXTENSIONS)
    return tuple(exts) if exts else ALL_EXTENSIONS
