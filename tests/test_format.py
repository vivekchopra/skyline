import json
import subprocess
from pathlib import Path

from skyline.cli import main
from skyline.demo_samples import PY_AFTER, PY_BEFORE

_GOLDEN = Path(__file__).parent / "golden" / "demo-python.json"


def _git(repo: Path, *args):
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "payments.py").write_text(PY_BEFORE, encoding="utf-8")
    _git(repo, "add", "payments.py")
    _git(repo, "commit", "-m", "before")
    (repo / "payments.py").write_text(PY_AFTER, encoding="utf-8")
    _git(repo, "add", "payments.py")
    _git(repo, "commit", "-m", "after")
    return repo


def test_diff_format_json_matches_demo_golden(tmp_path):
    repo = _repo(tmp_path)
    out = tmp_path / "report.json"
    rc = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD",
        "--format", "json", "--out", str(out),
    ])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert data["stats"] == golden["stats"]
    assert [row["crap"] for row in data["risk"]] == [row["crap"] for row in golden["risk"]]
    assert [row["name"] for row in data["risk"]] == [row["name"] for row in golden["risk"]]


def test_emit_prompt_alone_replaces_the_marker(tmp_path):
    repo = _repo(tmp_path)
    prompt = tmp_path / "review.md"
    rc = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD",
        "--emit-prompt", str(prompt),
    ])
    assert rc == 0
    text = prompt.read_text(encoding="utf-8")
    assert "{{SKYLINE_DATA}}" not in text
    assert text.startswith("# Skyline review")
    assert '"stats"' in text


def test_custom_template_missing_marker_fails(tmp_path):
    repo = _repo(tmp_path)
    template = tmp_path / "custom.md"
    template.write_text("no marker here\n", encoding="utf-8")
    rc = main([
        "diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD",
        "--emit-prompt", str(tmp_path / "out.md"),
        "--prompt-template", str(template),
    ])
    assert rc == 1
    assert not (tmp_path / "out.md").exists()
