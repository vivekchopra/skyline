import shutil

import pytest

from skyline.diff import diff_models
from skyline.python_extractor import extract_module as py_extract


def test_added_class():
    base = {"m.py": py_extract("m.py", "")}
    head = {"m.py": py_extract("m.py", "class New:\n    def go(self):\n        pass\n")}
    diff = diff_models(base, head)
    assert any(t.name == "New" and t.status == "added" for t in diff.types)


def test_removed_class():
    base = {"m.py": py_extract("m.py", "class Old:\n    pass\n")}
    head = {"m.py": py_extract("m.py", "")}
    diff = diff_models(base, head)
    assert any(t.name == "Old" and t.status == "removed" for t in diff.types)


def test_modified_method_signature():
    base = {"m.py": py_extract("m.py", "class A:\n    def f(self, x):\n        pass\n")}
    head = {"m.py": py_extract("m.py", "class A:\n    def f(self, x, y):\n        pass\n")}
    diff = diff_models(base, head)
    cls = next(t for t in diff.types if t.name == "A")
    assert cls.status == "modified"
    member = next(m for m in cls.members if m.name == "f")
    assert member.status == "modified"
    assert "params" in member.reason


def test_new_base_class_detected():
    base = {"m.py": py_extract("m.py", "class A:\n    pass\n")}
    head = {"m.py": py_extract("m.py", "class B:\n    pass\nclass A(B):\n    pass\n")}
    diff = diff_models(base, head)
    cls = next(t for t in diff.types if t.name == "A")
    assert cls.status == "modified"
    assert cls.added_relations == [("B", "extends")]


def test_unchanged_class_is_not_flagged():
    src = "class A:\n    def f(self):\n        pass\n"
    base = {"m.py": py_extract("m.py", src)}
    head = {"m.py": py_extract("m.py", src)}
    diff = diff_models(base, head)
    cls = next(t for t in diff.types if t.name == "A")
    assert cls.status == "unchanged"
    counts = diff.counts()
    assert all(v == 0 for v in counts.values())


@pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None,
    reason="TypeScript tests need Node.js + npm on PATH",
)
def test_typescript_extends_and_implements_diff():
    from skyline.ts_client import extract_modules

    base_src = "class Base {}\nclass A implements Base {}\n"
    head_src = "class Base {}\ninterface IFoo {}\nclass A extends Base implements IFoo {}\n"
    base = extract_modules({"a.ts": base_src})
    head = extract_modules({"a.ts": head_src})
    diff = diff_models(base, head)
    cls = next(t for t in diff.types if t.name == "A")
    assert cls.status == "modified"
    assert ("Base", "extends") in cls.added_relations
    assert ("IFoo", "implements") in cls.added_relations
