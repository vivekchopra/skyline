"""Command-line interface for skyline."""
from __future__ import annotations

import argparse
import sys

from pathlib import Path
from typing import Optional, TextIO

from .diff import diff_models
from .git_utils import changed_source_files, list_files_at_ref, list_tracked_source_files, origin_url, resolve_ref, rev_parse
from .languages import build_modules, extensions_for
from .policy import find_violations, load_policy
from .render_html import build_html_report
from .render_json import render_json
from .render_markdown import render_comment
from .review import build_review
from .snapshot import load_cached_map, save_cached_map, write_snapshot
from . import crap


def cmd_diff(args: argparse.Namespace) -> int:
    langs = args.lang if args.lang != ["auto"] else ["python", "typescript"]
    extensions = extensions_for(langs)

    snapshot_dir = getattr(args, "snapshot_dir", ".skyline")
    status = Status()
    try:
        try:
            args.base = _use_ref(args.repo, args.base)
            args.head = _use_ref(args.repo, args.head)
            status.update(f"Listing changes {args.base}...{args.head}")
            changed = changed_source_files(args.repo, args.base, args.head, extensions)
            base_sha = rev_parse(args.repo, args.base)
            head_sha = rev_parse(args.repo, args.head)
            base_modules = _modules_for_diff(
                args.repo, args.base, base_sha, extensions, snapshot_dir, status,
            )
            head_modules = _modules_for_diff(
                args.repo, args.head, head_sha, extensions, snapshot_dir, status,
            )
            base_sources = list_files_at_ref(args.repo, args.base, changed)
            head_sources = list_files_at_ref(args.repo, args.head, changed)
            status.update("Comparing maps")
        except Exception as exc:  # ToolingError etc. -- surface a clean message, not a traceback
            status.clear()
            print(f"error: {exc}", file=sys.stderr)
            return 1
    finally:
        status.clear()

    if not changed:
        print(f"No changed files ({', '.join(extensions)}) between the given refs.")

    diff = diff_models(base_modules, head_modules)
    policy_path = args.policy or str(Path(args.repo) / "skyline.policy.toml")
    policy = load_policy(policy_path)
    diff.violations = find_violations(diff, policy)
    coverage_map = crap.load_coverage_map(args.coverage)
    crap.annotate(diff, coverage_map)
    review = build_review(diff, base_sources, head_sources)
    remote = origin_url(args.repo)
    if args.format == "json":
        report = render_json(diff, args.base, args.head, review)
    else:
        report = build_html_report(
            diff, args.base, args.head, repo_label=args.repo, policy=policy, review=review,
            remote=remote, base_sha=base_sha, head_sha=head_sha,
        )

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    if args.comment:
        Path(args.comment).write_text(
            render_comment(
                diff, review, args.base, args.head,
                remote=remote, base_sha=base_sha, head_sha=head_sha,
            ), encoding="utf-8",
        )
        print(f"Wrote {args.comment}")

    counts = diff.counts()
    print(f"Wrote {args.out}")
    print(
        f"types: +{counts['types_added']} -{counts['types_removed']} ~{counts['types_modified']}  "
        f"functions: +{counts['functions_added']} -{counts['functions_removed']} ~{counts['functions_modified']}  "
        f"members: +{counts['members_added']} -{counts['members_removed']} ~{counts['members_modified']}"
    )
    new_violations = [v for v in diff.violations if v.is_new]
    if new_violations:
        print(f"policy violations: {len(new_violations)}")
    if args.fail_on_violation and new_violations:
        return 1
    return 0


class Status:
    """One rewriting status line on a terminal. A pipe gets one line per phase."""

    def __init__(self, stream: Optional[TextIO] = None, enabled: Optional[bool] = None):
        self.stream = sys.stderr if stream is None else stream
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self._width = 0
        self._phase = ""

    def update(self, message: str) -> None:
        if self.enabled:
            pad = " " * max(0, self._width - len(message))
            self.stream.write(f"\r{message}{pad}")
            self.stream.flush()
            self._width = len(message)
            return
        phase = message.split("  ", 1)[0]
        if phase != self._phase:
            self._phase = phase
            print(message, file=self.stream)

    def clear(self) -> None:
        if self.enabled and self._width:
            self.stream.write("\r" + " " * self._width + "\r")
            self.stream.flush()
            self._width = 0


def _modules_for_diff(repo: str, ref: str, sha: str, extensions, snapshot_dir: str, status: Status):
    """Full as-built map at ``ref``.

    A map already stored for this commit sha is reused. The sha is the checksum:
    a new commit misses the cache and is written under ``.skyline/maps/``.
    """
    loaded = load_cached_map(repo, snapshot_dir, sha)
    if loaded is not None:
        print(f"No change in {ref} ({sha[:12]}); loading previous run.")
        return loaded
    paths = list_tracked_source_files(repo, ref, extensions)
    total = len(paths)

    def on_read(done: int, count: int) -> None:
        status.update(f"Reading {ref}  {done}/{count}")

    if total == 0:
        status.update(f"Reading {ref}  0 files")
    files = list_files_at_ref(repo, ref, paths, on_file=on_read)

    def on_parse(done: int, count: int) -> None:
        status.update(f"Parsing {ref}  {done}/{count}")

    status.update(f"Parsing {ref}  0/{len(files)}")
    modules = build_modules(files, on_file=on_parse)
    save_cached_map(repo, snapshot_dir, ref, sha, modules)
    return modules


def _use_ref(repo: str, ref: str) -> str:
    resolved = resolve_ref(repo, ref)
    if resolved != ref:
        print(f"Using {resolved} for {ref}")
    return resolved


def cmd_snapshot(args: argparse.Namespace) -> int:
    langs = args.lang if args.lang != ["auto"] else ["python", "typescript"]
    extensions = extensions_for(langs)
    try:
        args.ref = _use_ref(args.repo, args.ref)
        model_path = write_snapshot(
            args.repo, args.ref, extensions, args.out_dir, render=args.render,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {model_path}")
    print(
        "Generated files are not a source of truth. Add .skyline/ to the examined "
        "repo's .gitignore, or check it in as a lockfile. Skyline does not choose for you."
    )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    if args.lang == "typescript":
        from .demo_samples import TS_AFTER, TS_BEFORE
        from .ts_client import extract_modules
        base_modules = extract_modules({"payments.ts": TS_BEFORE})
        head_modules = extract_modules({"payments.ts": TS_AFTER})
    else:
        from .demo_samples import PY_AFTER, PY_BEFORE
        from .python_extractor import extract_module
        base_modules = {"payments.py": extract_module("payments.py", PY_BEFORE)}
        head_modules = {"payments.py": extract_module("payments.py", PY_AFTER)}

    diff = diff_models(base_modules, head_modules)
    crap.annotate(diff, {})  # no coverage map for the demo: shows the 0%-assumed worst case
    report = build_html_report(diff, "before", "after", repo_label=f"skyline demo ({args.lang})")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote demo report to {args.out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="skyline",
        description="See how a change shapes the design, not just the lines.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_diff = sub.add_parser("diff", help="Diff two git refs and write an HTML report.")
    p_diff.add_argument("--repo", default=".", help="Path to the git repository (default: current directory).")
    p_diff.add_argument(
        "--base", required=True,
        help="Base ref, e.g. main or the PR's target branch. "
             "A name that exists on exactly one remote is read from that remote-tracking ref.",
    )
    p_diff.add_argument(
        "--head", required=True,
        help="Head ref, e.g. the PR branch or HEAD. "
             "A name that exists on exactly one remote is read from that remote-tracking ref.",
    )
    p_diff.add_argument("--out", default="skyline_report.html", help="Output file path. The format flag chooses the renderer, not this extension.")
    p_diff.add_argument(
        "--format", choices=["html", "json"], default="html",
        help="Report renderer (default: html). json is the structural model only.",
    )
    p_diff.add_argument(
        "--comment", default=None,
        help="Also write a markdown PR comment (violations, review order, Mermaid).",
    )
    p_diff.add_argument(
        "--lang", nargs="+", choices=["auto", "python", "typescript"], default=["auto"],
        help="Restrict analysis to one or more languages (default: auto, i.e. both).",
    )
    p_diff.add_argument(
        "--policy", default=None,
        help="Path to skyline.policy.toml (default: <repo>/skyline.policy.toml). "
             "A missing file draws no illegal edges.",
    )
    p_diff.add_argument(
        "--fail-on-violation", action="store_true",
        help="Exit 1 when this change introduces a policy violation. Default off. "
             "Does not fail on CRAP.",
    )
    p_diff.add_argument(
        "--snapshot-dir", default=".skyline",
        help="Directory of a previously written snapshot (default: .skyline). "
             "Used when its ref matches; otherwise skyline extracts.",
    )
    p_diff.add_argument(
        "--coverage", default=None,
        help="Optional path to a coverage map JSON file (see README: 'Coverage input'). "
             "Members/functions not present in it are scored assuming 0%% coverage.",
    )
    p_diff.set_defaults(func=cmd_diff)

    p_snap = sub.add_parser("snapshot", help="Write the as-built model for one git ref.")
    p_snap.add_argument("--repo", default=".", help="Path to the git repository (default: current directory).")
    p_snap.add_argument("--ref", default="HEAD", help="Git ref to snapshot (default: HEAD).")
    p_snap.add_argument(
        "--out-dir", default=".skyline",
        help="Output directory inside the examined repo (default: .skyline). "
             "Override with docs/architecture if the owner wants the render in docs/.",
    )
    p_snap.add_argument(
        "--lang", nargs="+", choices=["auto", "python", "typescript"], default=["auto"],
        help="Restrict analysis to one or more languages (default: auto, i.e. both).",
    )
    p_snap.add_argument(
        "--render", action="store_true",
        help="Also write map.md (Mermaid) and map.svg. The JSON model stays the IR.",
    )
    p_snap.set_defaults(func=cmd_snapshot)

    p_demo = sub.add_parser("demo", help="Generate a demo report from bundled sample code (no git needed).")
    p_demo.add_argument("--out", default="skyline_demo.html", help="Output HTML file path.")
    p_demo.add_argument("--lang", choices=["python", "typescript"], default="python")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
