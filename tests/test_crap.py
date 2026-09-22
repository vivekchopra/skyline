from skyline import crap
from skyline.diff import diff_models
from skyline.python_extractor import extract_module


def test_score_formula():
    s = crap.score(complexity=10, coverage=0.0)
    assert s.value == 110.0  # 10^2 * 1 + 10
    assert s.band == "severe"


def test_score_with_coverage_reduces_value():
    s = crap.score(complexity=10, coverage=0.9)
    assert abs(s.value - 10.1) < 0.01  # 10^2 * 0.1^3 + 10
    assert s.coverage_supplied is True


def test_missing_coverage_treated_as_zero():
    with_none = crap.score(complexity=4, coverage=None)
    with_zero = crap.score(complexity=4, coverage=0.0)
    assert with_none.value == with_zero.value
    assert with_none.coverage_supplied is False
    assert with_zero.coverage_supplied is True


def test_none_complexity_yields_no_score():
    assert crap.score(complexity=None, coverage=0.5) is None


def test_bands_are_ordered_correctly():
    assert crap.score(1, 0.0).band == "low"       # crap = 2
    assert crap.score(2, 0.0).band == "moderate"   # crap = 2^2+2 = 6
    assert crap.score(10, 0.0).band == "severe"    # crap = 110


def test_annotate_scores_added_and_modified_only():
    base = {"m.py": extract_module("m.py", "class A:\n    def old(self):\n        pass\n")}
    head = {"m.py": extract_module(
        "m.py",
        "class A:\n"
        "    def old(self):\n"
        "        pass\n"
        "    def new(self, x):\n"
        "        if x:\n"
        "            return 1\n"
        "        return 0\n",
    )}
    diff = diff_models(base, head)
    crap.annotate(diff, {})
    cls = next(t for t in diff.types if t.name == "A")
    old_member = next(m for m in cls.members if m.name == "old")
    new_member = next(m for m in cls.members if m.name == "new")
    assert old_member.status == "unchanged"
    assert old_member.crap is None  # unchanged members aren't scored
    assert new_member.crap is not None
    assert new_member.crap.value == 6.0  # complexity 2 -> 2^2*1+2 = 6


def test_annotate_uses_coverage_map():
    base = {"m.py": extract_module("m.py", "")}
    head = {"m.py": extract_module("m.py", "class A:\n    def f(self):\n        pass\n")}
    diff = diff_models(base, head)
    cls_qualname = next(t for t in diff.types if t.name == "A").qualname
    crap.annotate(diff, {f"{cls_qualname}.f": 1.0})
    member = next(t for t in diff.types if t.name == "A").members[0]
    assert member.crap.coverage == 1.0
    assert member.crap.value == 1.0  # fully covered, complexity 1 -> 1
