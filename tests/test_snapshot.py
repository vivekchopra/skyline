import json
import subprocess
from pathlib import Path

from skyline.cli import main
from skyline.git_utils import changed_source_files
from skyline.python_extractor import extract_module
from skyline.serialize import dump_modules, load_modules
from skyline.snapshot import load_fresh_snapshot


def _git(repo: Path, *args):
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


def test_round_trip_model_json():
    source = "class A:\n    def f(self):\n        return 1\n\ndef helper():\n    return 2\n"
    modules = {"m.py": extract_module("m.py", source)}
    raw = dump_modules(modules, ref="HEAD", sha="abc")
    ref, sha, loaded = load_modules(raw)
    assert ref == "HEAD"
    assert sha == "abc"
    assert loaded == modules


def test_snapshot_includes_file_outside_the_three_dot_diff(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / "keep.py").write_text("class Kept:\n    pass\n", encoding="utf-8")
    (repo / "change.py").write_text("class Old:\n    pass\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    (repo / "change.py").write_text("class New:\n    pass\n", encoding="utf-8")
    _git(repo, "add", "change.py")
    _git(repo, "commit", "-m", "edit")

    out = repo / ".skyline"
    rc = main(["snapshot", "--repo", str(repo), "--ref", "HEAD", "--out-dir", str(out)])
    assert rc == 0
    data = json.loads((out / "model.json").read_text(encoding="utf-8"))
    assert "keep.py" in data["modules"]
    assert "change.py" in data["modules"]
    changed = changed_source_files(str(repo), "HEAD~1", "HEAD", (".py",))
    assert "keep.py" not in changed
    assert "change.py" in changed

    loaded = load_fresh_snapshot(str(repo), "HEAD", str(out))
    assert loaded is not None
    assert "keep.py" in loaded

    first = main(["diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD", "--out", str(tmp_path / "a.html")])
    assert first == 0
    capsys.readouterr()
    second = main(["diff", "--repo", str(repo), "--base", "HEAD~1", "--head", "HEAD", "--out", str(tmp_path / "b.html")])
    assert second == 0
    assert "loading previous run" in capsys.readouterr().out
