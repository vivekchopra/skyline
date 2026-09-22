# ADR 0002: CLI kernel, CI as the reviewer surface, skill as the author surface

## Status

Accepted

## Date

2026-09-20

## Amended

2026-09-21: follow-up points at [docs/plan.md](../plan.md); product content lives in [ADR 0001](0001-map-policy-overlay.md).

## Context

ADR 0001 decides *what* Skyline should show (as-built map, policy, PR overlay). This ADR decides *where that picture has to live* so an architect or a developer actually sees it.

Three moments of use:

| Moment | Who | What he or she will do |
| --- | --- | --- |
| Before the PR | Author (or an agent in Cursor) | Will not remember a one-off CLI unless it is in the loop he or she already uses |
| On every push | Nobody watching | Must run unattended, on the same three-dot range GitHub shows |
| During review | Human on the GitHub PR | Will not `pip install`, will not open Actions artifacts |

v1 is a pip CLI plus a workflow that uploads an HTML artifact. That is a kernel without a reviewer surface. A Cursor skill without CI would invert the mistake: the author sees it, every other reviewer does not.

A skill is instructions for an agent (`SKILL.md`). It is not an analyzer. If the skill “reviews PRs” by eyeballing the diff in-context, the structural model, CRAP, policy violations, and a stable diagram are thrown away. If the skill shells out to `skyline`, it is a trigger, not a second product.

An MCP server would expose the same CLI as a tool. Extra surface for a binary that already has a clean argv. Defer until an agent needs structured JSON more than HTML/markdown.

A standalone GUI or editor extension is a third renderer and a third install path. The HTML report is the interactive artifact. Becoming Uncle Bob’s live uml-viewer window is out of scope (ADR 0001).

## Decision

**One kernel, two distributions. Not three products.**

```text
Cursor skill  ──invokes──►  skyline CLI  ◄──invokes──  GitHub Action
   (author)                  (kernel)                    (reviewer)
                                │
                                ├── HTML + SVG  (full report, neighborhood map)
                                └── markdown + Mermaid  (PR comment: overlay + violations)
```

1. **Kernel: standalone CLI** (`pip install skyline`). Extraction, snapshot, policy check, diff, CRAP, and rendering live here. Testable, composable, no GitHub or Cursor dependency.

2. **Primary reviewer surface: CI step that comments on the PR.** The workflow in [`.github/workflows/skyline.yml`](../../.github/workflows/skyline.yml) is the right *kind* of thing and the wrong *finish* until it posts a sticky comment. Permissions: `pull-requests: write`. One comment updated per push, not a new comment each time. Install from the PR checkout (`pip install .`) so the comment matches the branch under review.

3. **Author/agent surface: a project skill** (`.cursor/skills/skyline/SKILL.md`) that tells the agent *when* to run the CLI (review this PR, snapshot this repo, check design before opening a PR) and *how* to read the report: violations first, then the ADR 0001 review order. The skill must not skip the CLI and “just read the diff.”

### Do not

- Make Skyline Cursor-only. Most reviewers are on GitHub.
- Replace the CLI with a prompt.
- Build an MCP server, VS Code extension, or GUI in the implementation plan.
- Gate merge on CRAP thresholds. Opt-in fail is for **policy violations** only (ADR 0001).
- Publish a marketplace Action until the in-repo comment path is proven.

### Install UX by audience

- **This repo:** workflow file + project skill checked in; `pip install -e .` for local/agent runs.
- **Other repos (later):** reusable Action (`uses: vivekchopra/skyline@v1`) wrapping the CLI. The adopting repo does not need a skill.
- **Ad-hoc:** `skyline snapshot`, `skyline diff`, `skyline demo`.

## Consequences

### Positive

- Reviewers see the overlay where review already happens (the PR thread).
- An author or agent can get the same picture before push, from the same code path.
- One test surface (the CLI). Skill and Action cannot drift in analysis, only at invocation time.

### Negative / trade-offs

- Two invocation sites (Action + skill). Both are thin wrappers around `skyline diff --comment …`.
- A project skill only helps a person who opens this repo in Cursor. He or she is an author. Reviewers are covered by CI.

## Alternatives considered

- **CLI only.** Nobody runs it.
- **Skill only.** GitHub reviewers see nothing.
- **CI only.** The 600-line PR is already written; the comment is a surprise.
- **MCP as the product.** Redundant while HTML/markdown/exit codes suffice.
- **GitHub App.** Revisit if the Action outgrows workflow files.

## Follow-up

[docs/plan.md](../plan.md): the CI comment and the skill are steps in that single sequence, not a separate project.
