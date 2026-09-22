import shutil

import pytest

from skyline import crap
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


def test_complexity_change_is_modified_and_scored():
    base_src = "class A:\n    def f(self):\n        if True:\n            return 1\n        return 0\n"
    head_ifs = "\n".join("        if True:\n            return 1" for _ in range(17))
    head_src = f"class A:\n    def f(self):\n{head_ifs}\n        return 0\n"
    diff = diff_models(
        {"m.py": py_extract("m.py", base_src)},
        {"m.py": py_extract("m.py", head_src)},
    )
    cls = next(t for t in diff.types if t.name == "A")
    member = next(m for m in cls.members if m.name == "f")
    assert member.before.complexity == 2
    assert member.after.complexity == 18
    assert member.status == "modified"
    assert "complexity 2 \u2192 18" in member.reason
    crap.annotate(diff, {})
    assert member.crap is not None


def test_body_hash_change_is_modified_and_scored():
    base_src = "class A:\n    def f(self):\n        x = 1\n        return x\n"
    head_src = "class A:\n    def f(self):\n        x = 2\n        return x\n"
    diff = diff_models(
        {"m.py": py_extract("m.py", base_src)},
        {"m.py": py_extract("m.py", head_src)},
    )
    member = next(m for m in next(t for t in diff.types if t.name == "A").members if m.name == "f")
    assert member.before.complexity == member.after.complexity
    assert member.before.body_hash != member.after.body_hash
    assert member.status == "modified"
    assert member.reason == "body changed"
    crap.annotate(diff, {})
    assert member.crap is not None


def test_identical_body_is_unchanged_and_unscored():
    src = "class A:\n    def f(self):\n        x = 1\n        return x\n"
    diff = diff_models(
        {"m.py": py_extract("m.py", src)},
        {"m.py": py_extract("m.py", src)},
    )
    cls = next(t for t in diff.types if t.name == "A")
    member = next(m for m in cls.members if m.name == "f")
    assert cls.status == "unchanged"
    assert member.status == "unchanged"
    crap.annotate(diff, {})
    assert member.crap is None


def test_class_decorator_change_modifies_type():
    base = {"m.py": py_extract("m.py", "class A:\n    pass\n")}
    head = {"m.py": py_extract("m.py", "@dataclass\nclass A:\n    pass\n")}
    diff = diff_models(base, head)
    cls = next(t for t in diff.types if t.name == "A")
    assert cls.status == "modified"
    assert "decorators" in cls.reason


def test_dunder_stays_public_and_underscore_is_internal():
    src = "class A:\n    def __init__(self):\n        pass\n    def _hidden(self):\n        pass\n"
    mod = py_extract("m.py", src)
    assert mod.types["A"].members["__init__"].exported is True
    assert mod.types["A"].members["_hidden"].exported is False


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
