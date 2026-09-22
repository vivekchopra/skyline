---
name: skyline
description: >-
  Run the skyline CLI to snapshot an as-built map, diff a change against
  that map and skyline.policy.toml, and report policy violations first.
  Use when reviewing a pull request, snapshotting this repo, or checking
  design before opening a PR.
---

# Skyline

This skill is a trigger. Skyline is the CLI. Do not review a diff by reading hunks in place of the report. The structural model, CRAP scores, policy violations, and the diagram come from the command, not from eyeballing the patch.

## When to run

- Review this PR
- Snapshot the architecture
- Check design or risk before opening a PR

## Commands

From this checkout (`pip install -e .` if `skyline` is not on `PATH`):

```bash
skyline snapshot --repo . --ref HEAD --out-dir .skyline
skyline diff --repo . --base <base> --head <head> --out skyline_report.html --comment skyline_comment.md
```

Use the PR's three-dot range: `--base` is the target branch, `--head` is the branch under review. Add `--fail-on-violation` only when a `skyline.policy.toml` exists and a new illegal edge should fail the run. Do not fail on CRAP.

## How to read the report

Report in this order, from the HTML or the comment file. Do not skip ahead to the line diff.

1. New policy violations (illegal edges, wrong-package types, layer-crossing cycles)
2. Breaking public signature, heritage, or schema changes
3. High CRAP on added and body-modified units
4. New coupling that is legal but worth seeing
5. Untested new types
6. Everything else
