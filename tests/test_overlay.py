import subprocess
from pathlib import Path

from skyline.cli import main


def _git(repo: Path, *args):
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


def _init(repo: Path):
    repo.mkdir()
    _git(repo, "init")


def test_unchanged_base_class_stays_in_the_neighborhood(tmp_path):
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "parent.py").write_text("class Parent:\n    pass\n", encoding="utf-8")
    (repo / "child.py").write_text("class Child:\n    pass\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    (repo / "child.py").write_text("class Child(Parent):\n    pass\n", encoding="utf-8")
    _git(repo, "add", "child.py")
    _git(repo, "commit", "-m", "subclass")

    out = tmp_path / "report.html"
    rc = main(["diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD", "--out", str(out)])
    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert "Parent" in html
    assert "child.py" in html


def test_fail_on_violation_and_coupling_without_policy(tmp_path):
    repo = tmp_path / "repo"
    _init(repo)
    (repo / "domain").mkdir()
    (repo / "infra").mkdir()
    (repo / "domain" / "a.py").write_text("class UseCase:\n    pass\n", encoding="utf-8")
    (repo / "infra" / "b.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "skyline.policy.toml").write_text('layers = ["domain", "infra"]\n', encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    (repo / "domain" / "a.py").write_text(
        "from infra.b import x\nclass UseCase:\n    pass\n", encoding="utf-8"
    )
    _git(repo, "add", "domain/a.py")
    _git(repo, "commit", "-m", "illegal import")

    out = tmp_path / "report.html"
    rc = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD",
        "--out", str(out), "--fail-on-violation",
    ])
    assert rc == 1
    html = out.read_text(encoding="utf-8")
    assert "Policy violations" in html
    assert "Illegal edge" in html
    assert html.index("Policy violations") < html.index("Classes")

    rc_visible = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD", "--out", str(out),
    ])
    assert rc_visible == 0

    policy = repo / "skyline.policy.toml"
    policy.unlink()
    bare = tmp_path / "bare.html"
    rc_bare = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD",
        "--out", str(bare), "--fail-on-violation",
    ])
    assert rc_bare == 0
    bare_html = bare.read_text(encoding="utf-8")
    assert "<h2>Policy violations</h2>" not in bare_html
    assert "domain/a.py" in bare_html and "infra/b.py" in bare_html
