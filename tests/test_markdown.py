from skyline.diff import diff_models
from skyline.policy import find_violations, parse_policy
from skyline.python_extractor import extract_module as py_extract
from skyline.render_markdown import MARKER, render_comment
from skyline.review import build_review


def test_comment_has_marker_and_violation_heading():
    policy = parse_policy('layers = ["domain", "infra"]\n')
    base = {
        "domain/a.py": py_extract("domain/a.py", "class UseCase:\n    pass\n"),
        "infra/b.py": py_extract("infra/b.py", "x = 1\n"),
    }
    head = {
        "domain/a.py": py_extract("domain/a.py", "from infra.b import x\nclass UseCase:\n    pass\n"),
        "infra/b.py": py_extract("infra/b.py", "x = 1\n"),
    }
    diff = diff_models(base, head)
    diff.violations = find_violations(diff, policy)
    review = build_review(diff, {}, {})
    text = render_comment(diff, review, "main", "head")
    assert MARKER in text
    assert "How to review:" in text
    assert text.index("How to review:") < text.index("### Policy violations")
    assert "### Policy violations" in text
    assert text.index("### Policy violations") < text.index("### Overlay")
