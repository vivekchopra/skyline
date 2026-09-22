from skyline.diff import diff_models
from skyline.policy import find_violations, parse_policy
from skyline.python_extractor import extract_module as py_extract


def _pair(base_src: str, head_src: str, path: str, other: dict):
    base = {path: py_extract(path, base_src), **{p: py_extract(p, s) for p, s in other.items()}}
    head = {path: py_extract(path, head_src), **{p: py_extract(p, s) for p, s in other.items()}}
    return diff_models(base, head)


def test_inner_to_outer_is_a_violation():
    policy = parse_policy('layers = ["domain", "infra"]\n')
    diff = _pair(
        "",
        "from infra.b import x\n",
        "domain/a.py",
        {"infra/b.py": "x = 1\n"},
    )
    violations = find_violations(diff, policy)
    assert any(v.kind == "illegal_edge" and v.is_new for v in violations)
    assert any("domain/a.py" in v.message and "infra/b.py" in v.message for v in violations)


def test_same_rank_import_is_allowed():
    policy = parse_policy(
        "\n".join([
            "[layer.billing]",
            "rank = 1",
            'prefixes = ["billing/"]',
            "",
            "[layer.shipping]",
            "rank = 1",
            'prefixes = ["shipping/"]',
            "",
        ])
    )
    diff = _pair(
        "",
        "from shipping.b import x\n",
        "billing/a.py",
        {"shipping/b.py": "x = 1\n"},
    )
    assert find_violations(diff, policy) == []


def test_missing_policy_has_no_violations():
    diff = _pair(
        "",
        "from infra.b import x\n",
        "domain/a.py",
        {"infra/b.py": "x = 1\n"},
    )
    assert find_violations(diff, None) == []
    assert any(i.status == "added" and i.target == "infra/b.py" for i in diff.imports)


def test_proposal_is_not_a_layer():
    policy = parse_policy(
        'layers = ["domain", "infra"]\n\n[proposals]\nengine = "not instantiated"\n'
    )
    assert policy.layer_for("engine/a.py") is None
    assert "engine" not in policy.layers
    assert policy.proposals["engine"] == "not instantiated"
