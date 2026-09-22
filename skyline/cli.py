"""Command-line interface for skyline."""
from __future__ import annotations

import argparse
import sys

from .diff import diff_models
from .git_utils import changed_source_files, list_files_at_ref
from .languages import build_modules, extensions_for
from .render_html import build_html_report
from . import crap


def cmd_diff(args: argparse.Namespace) -> int:
    langs = args.lang if args.lang != ["auto"] else ["python", "typescript"]
    extensions = extensions_for(langs)

    changed = changed_source_files(args.repo, args.base, args.head, extensions)
    if not changed:
        print(f"No changed files ({', '.join(extensions)}) between the given refs.")

    base_files = list_files_at_ref(args.repo, args.base, changed)
    head_files = list_files_at_ref(args.repo, args.head, changed)

    try:
        base_modules = build_modules(base_files)
        head_modules = build_modules(head_files)
    except Exception as exc:  # ToolingError etc. -- surface a clean message, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1

    diff = diff_models(base_modules, head_modules)
    coverage_map = crap.load_coverage_map(args.coverage)
    crap.annotate(diff, coverage_map)
    report = build_html_report(diff, args.base, args.head, repo_label=args.repo)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)

    counts = diff.counts()
    print(f"Wrote {args.out}")
    print(
        f"types: +{counts['types_added']} -{counts['types_removed']} ~{counts['types_modified']}  "
        f"functions: +{counts['functions_added']} -{counts['functions_removed']} ~{counts['functions_modified']}  "
        f"members: +{counts['members_added']} -{counts['members_removed']} ~{counts['members_modified']}"
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
    p_diff.add_argument("--base", required=True, help="Base ref, e.g. main or the PR's target branch.")
    p_diff.add_argument("--head", required=True, help="Head ref, e.g. the PR branch or HEAD.")
    p_diff.add_argument("--out", default="skyline_report.html", help="Output HTML file path.")
    p_diff.add_argument(
        "--lang", nargs="+", choices=["auto", "python", "typescript"], default=["auto"],
        help="Restrict analysis to one or more languages (default: auto, i.e. both).",
    )
    p_diff.add_argument(
        "--coverage", default=None,
        help="Optional path to a coverage map JSON file (see README: 'Coverage input'). "
             "Members/functions not present in it are scored assuming 0%% coverage.",
    )
    p_diff.set_defaults(func=cmd_diff)

    p_demo = sub.add_parser("demo", help="Generate a demo report from bundled sample code (no git needed).")
    p_demo.add_argument("--out", default="skyline_demo.html", help="Output HTML file path.")
    p_demo.add_argument("--lang", choices=["python", "typescript"], default="python")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
