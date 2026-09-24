from skyline import crap
from skyline.diff import diff_models
from skyline.python_extractor import extract_module as py_extract
from skyline.review import build_review


def test_caption_counts_changed_files():
    base = {"a.py": "class A:\n    pass\n", "b.py": "x = 1\n"}
    head = {"a.py": "class A:\n    def f(self, y):\n        return y\n", "b.py": "x = 1\n"}
    diff = diff_models(
        {path: py_extract(path, src) for path, src in base.items()},
        {path: py_extract(path, src) for path, src in head.items()},
    )
    review = build_review(diff, base, head)
    assert review.caption.startswith("1 file changed")


def test_signature_change_is_breaking_and_body_only_is_not():
    base_src = "class A:\n    def f(self, x):\n        return x\n    def g(self):\n        return 1\n"
    head_src = "class A:\n    def f(self, x, y):\n        return x\n    def g(self):\n        return 2\n"
    diff = diff_models(
        {"m.py": py_extract("m.py", base_src)},
        {"m.py": py_extract("m.py", head_src)},
    )
    crap.annotate(diff, {})
    review = build_review(diff, {"m.py": base_src}, {"m.py": head_src})
    assert any("m.py::A.f" in line and "breaking" in line for line in review.breaking)
    assert not any("m.py::A.g" in line for line in review.breaking)
    assert review.chips["m.py::A.g"] == ["body"]


def test_breaking_row_names_files_that_import_it():
    base = {
        "a.py": "from b import B\n",
        "b.py": "class B:\n    def f(self, x):\n        return x\n",
        "c.py": "class C:\n    def g(self, x):\n        return x\n",
    }
    head = {
        "a.py": "from b import B\n",
        "b.py": "class B:\n    def f(self, x, y):\n        return x\n",
        "c.py": "class C:\n    def g(self, x, y):\n        return x\n",
    }
    diff = diff_models(
        {path: py_extract(path, src) for path, src in base.items()},
        {path: py_extract(path, src) for path, src in head.items()},
    )
    review = build_review(diff, base, head)
    imported = next(line for line in review.breaking if "b.py::B.f" in line)
    alone = next(line for line in review.breaking if "c.py::C.g" in line)
    assert imported.endswith("\u00b7 1 dependent")
    assert "dependent" not in alone
    assert review.breaking.index(imported) < review.breaking.index(alone)


def test_new_type_mentioned_in_a_changed_test_is_not_untested():
    base = {
        "app.py": "",
        "tests/test_app.py": "",
    }
    head = {
        "app.py": "class Widget:\n    pass\n",
        "tests/test_app.py": "from app import Widget\n",
    }
    diff = diff_models(
        {path: py_extract(path, src) for path, src in base.items()},
        {path: py_extract(path, src) for path, src in head.items()},
    )
    covered = build_review(diff, base, head)
    assert covered.untested == []

    head["tests/test_app.py"] = "def test_nothing():\n    assert True\n"
    bare = diff_models(
        {path: py_extract(path, src) for path, src in base.items()},
        {path: py_extract(path, src) for path, src in head.items()},
    )
    missed = build_review(bare, base, head)
    assert missed.untested == ["app.py::Widget"]
