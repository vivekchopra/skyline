import pytest

from skyline import crap
from skyline.demo_samples import PY_AFTER, PY_BEFORE
from skyline.diff import diff_models
from skyline.python_extractor import extract_module
from skyline.render_json import render_json
from skyline.render_prompt import MARKER, load_template, render_prompt
from skyline.review import build_review


def _demo():
    base = {"payments.py": extract_module("payments.py", PY_BEFORE)}
    head = {"payments.py": extract_module("payments.py", PY_AFTER)}
    diff = diff_models(base, head)
    crap.annotate(diff, {})
    review = build_review(diff, {"payments.py": PY_BEFORE}, {"payments.py": PY_AFTER})
    return diff, review


def test_default_template_replaces_the_marker():
    diff, review = _demo()
    text = render_prompt(diff, "before", "after", review, load_template())
    assert MARKER not in text
    assert render_json(diff, "before", "after", review).strip() in text
    assert text.startswith("# Skyline review")


def test_custom_template_without_the_marker_fails():
    diff, review = _demo()
    with pytest.raises(ValueError, match="SKYLINE_DATA"):
        render_prompt(diff, "before", "after", review, "rank these somehow\n")
