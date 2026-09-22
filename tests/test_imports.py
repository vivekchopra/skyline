import shutil

import pytest

from skyline.diff import diff_models
from skyline.python_extractor import extract_module as py_extract


def test_python_import_resolves_to_module_file():
    base = {
        "pkg/a.py": py_extract("pkg/a.py", ""),
        "pkg/b.py": py_extract("pkg/b.py", "x = 1\n"),
    }
    head = {
        "pkg/a.py": py_extract("pkg/a.py", "from pkg.b import x\n"),
        "pkg/b.py": py_extract("pkg/b.py", "x = 1\n"),
    }
    diff = diff_models(base, head)
    assert any(
        i.source == "pkg/a.py" and i.target == "pkg/b.py" and i.status == "added"
        for i in diff.imports
    )


def test_python_third_party_import_is_dropped():
    base = {"a.py": py_extract("a.py", "")}
    head = {"a.py": py_extract("a.py", "import react\n")}
    diff = diff_models(base, head)
    assert diff.imports == []


def test_python_package_init_resolves():
    base = {
        "pkg/a.py": py_extract("pkg/a.py", ""),
        "pkg/b/__init__.py": py_extract("pkg/b/__init__.py", "x = 1\n"),
    }
    head = {
        "pkg/a.py": py_extract("pkg/a.py", "from pkg.b import x\n"),
        "pkg/b/__init__.py": py_extract("pkg/b/__init__.py", "x = 1\n"),
    }
    diff = diff_models(base, head)
    assert any(i.target == "pkg/b/__init__.py" and i.status == "added" for i in diff.imports)


@pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None,
    reason="TypeScript tests need Node.js + npm on PATH",
)
def test_typescript_relative_import_resolves_and_bare_import_does_not():
    from skyline.ts_client import extract_modules

    base = extract_modules({
        "pkg/a.ts": "export const n = 1;\n",
        "pkg/b.ts": "export const x = 1;\n",
    })
    head = extract_modules({
        "pkg/a.ts": "import { x } from './b';\nimport React from 'react';\nexport const n = 1;\n",
        "pkg/b.ts": "export const x = 1;\n",
    })
    diff = diff_models(base, head)
    assert any(
        i.source == "pkg/a.ts" and i.target == "pkg/b.ts" and i.status == "added"
        for i in diff.imports
    )
    assert all("react" not in i.target for i in diff.imports)


def test_two_cycle_is_drawn_thicker():
    from skyline.render_svg import build_diagram_svg

    base = {
        "pkg/a.py": py_extract("pkg/a.py", "class A:\n    pass\n"),
        "pkg/b.py": py_extract("pkg/b.py", "class B:\n    pass\n"),
    }
    head = {
        "pkg/a.py": py_extract("pkg/a.py", "from pkg.b import B\nclass A:\n    pass\n"),
        "pkg/b.py": py_extract("pkg/b.py", "from pkg.a import A\nclass B:\n    pass\n"),
    }
    svg = build_diagram_svg(diff_models(base, head))
    assert 'stroke-width="2.6"' in svg
