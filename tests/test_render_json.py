import json
import shutil
from pathlib import Path

import pytest

from skyline import crap
from skyline.demo_samples import PY_AFTER, PY_BEFORE, TS_AFTER, TS_BEFORE
from skyline.diff import diff_models
from skyline.python_extractor import extract_module
from skyline.render_html import build_html_report
from skyline.render_json import render_json
from skyline.review import build_review

_GOLDEN = Path(__file__).parent / "golden"
_needs_node = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npm") is None,
    reason="TypeScript demo needs node and npm",
)


def _python_diff():
    base = {"payments.py": extract_module("payments.py", PY_BEFORE)}
    head = {"payments.py": extract_module("payments.py", PY_AFTER)}
    diff = diff_models(base, head)
    crap.annotate(diff, {})
    review = build_review(diff, {"payments.py": PY_BEFORE}, {"payments.py": PY_AFTER})
    return diff, review


def _typescript_diff():
    from skyline.ts_client import extract_modules
    base = extract_modules({"payments.ts": TS_BEFORE})
    head = extract_modules({"payments.ts": TS_AFTER})
    diff = diff_models(base, head)
    crap.annotate(diff, {})
    review = build_review(diff, {"payments.ts": TS_BEFORE}, {"payments.ts": TS_AFTER})
    return diff, review


def _assert_agrees(diff, review, lang: str):
    raw = render_json(diff, "before", "after", review)
    data = json.loads(raw)
    html = build_html_report(diff, "before", "after", repo_label=f"skyline demo ({lang})", review=review)
    for key, value in data["stats"].items():
        if value:
            assert f">{value}<" in html or f'class="n">{value}<' in html
    for row in data["risk"]:
        assert row["crap"]["label"] in html
    for fn in data["functions"]:
        if fn["crap"]:
            assert fn["crap"]["label"] in html
    for typ in data["types"]:
        for member in typ["members"]:
            if member["crap"]:
                assert member["crap"]["label"] in html
    golden = _GOLDEN / f"demo-{lang}.json"
    assert raw == golden.read_text(encoding="utf-8")
    assert len(data["risk"]) >= len(review.risks)


def test_python_json_matches_html_and_golden():
    diff, review = _python_diff()
    _assert_agrees(diff, review, "python")


@_needs_node
def test_typescript_json_matches_html_and_golden():
    diff, review = _typescript_diff()
    _assert_agrees(diff, review, "typescript")
