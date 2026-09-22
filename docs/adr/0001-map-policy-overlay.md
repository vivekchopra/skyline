# ADR 0001: Map, policy, and PR overlay: make architecture drift visible

## Status

Accepted

## Date

2026-09-21

## Supersedes

The 2026-09-20 text of this decision (signature-only PR delta, parse-changed-files-only, “not a whole-repo UML browser”). That text under-specified the product: a delta with no city is not how a change shapes the design.

## Context

Skyline exists because AI-assisted PRs are large and agents do not share an architect’s sense of **where code belongs**. The tagline is: *See how a change shapes the design, not just the lines.*

v1 diffs **type signatures and heritage** in files that already changed, paints UML, and overlays CRAP. That is a developer lens on a hunk list. It does not catch the slop an architect cares about: a use-case in the wrong package, a new import inner→outer, a table owned by the wrong bounded context. CRAP on a new method does not catch that. A grey “external” box for a base class name does not catch that.

Robert C. Martin (Uncle Bob) reviews agent-built projects by living in a **live map of the whole system** ([uml-viewer](https://github.com/unclebob/uml-viewer), [crap4clj](https://github.com/unclebob/crap4clj)). He generates topology from source plus a small **policy** (layer order, dependency rule). He does not hand-edit the generated IR. He gitignores the viewer install and commits metrics. He paints violating edges red. He drills into source from the diagram. He is not reading the GitHub hunk view.

Skyline is the **PR-shaped** version of that idea, not a clone of his live agent IDE. The architect still needs a known design. The reviewer still needs the delta **on** that design, on the pull request, because that is where review happens.

Git already stores both trees. “Parse only changed files” was a speed trick, not a product constraint. The slogan requires a baseline.

## Decision

Skyline’s review model is three artifacts, then a coloring:

```text
as-intended policy          (small, hand-maintained, checked in)
        +
as-built map of base        (generated from the whole tree at merge-base)
        +
as-built map of head        (generated from the whole tree at the PR)
        →
delta painted on the map, judged against the policy
```

Keep the tagline. Widen “shape” from **signatures in changed files** to **what this change did to the known design, and whether that is allowed.**

### 1. As-built map (generated, do not hand-edit)

Extract the language-agnostic model (`ModuleModel`: types, members, functions, imports) for **every** matching source file at a git ref, not only the files in the three-dot diff.

Commands:

- `skyline snapshot`: write the as-built model (and optional Mermaid/SVG render) for `--ref` (default `HEAD`).
- `skyline diff`: build as-built at `--base` and `--head` (or load snapshots if present and fresh) and overlay.

Default output directory: **`.skyline/`** in the examined repo (the repo under review, not this one). Optional `--architecture-dir docs/architecture` if the owner of that repo wants the render in `docs/`. Skyline never treats generated UML as source of truth. Regenerating must be lossless relative to source + policy.

The owner of the examined repo chooses whether generated files are gitignored or checked in. Checking those files in is a lockfile: onboarding and “the map itself moved in this PR.” Ignoring those files is fine if CI always regenerates. Recommend a comment in the examined repo’s `.gitignore`, not a silent tool-written ignore that hides the choice.

### 2. As-intended policy (the known architecture)

A small checked-in file at the examined repo root, default **`skyline.policy.toml`**:

- **Packages / layers**: names that already exist in the tree (path prefixes or Python packages). Do not invent Domain / Engine / Adapters boxes that are not in the code. If the owner of the repo wants a grouping that is not in the tree, mark it as a **proposal** (view-only, labeled not instantiated), the way Bob does: do not fake namespaces.
- **Levels / allowed edges**: which layer may depend on which. A new or remaining edge that points the forbidden way is a **violation**. Same-rank is allowed unless the policy says otherwise.
- Optional omit lists (generated noise, third-party).

No policy means: still show the as-built map and the PR overlay; draw no red “illegal” edges. Policy is how an architect **throttles slop**. Pictures without a rule are architecture theater.

### 3. PR overlay (what the reviewer sees)

Default display is still the **delta**, not 400 boxes in a GitHub comment:

- Types / functions / members added, removed, modified (including **body and complexity** changes, not only signatures).
- Import edges added, removed, or cyclic, resolved among files in the as-built maps.
- Neighborhood: unchanged types that a changed type extends, implements, or newly imports, so the plug-in point is visible.
- **Policy violations first**: new illegal edges, new types in the wrong package, new cycles that cross layers.
- CRAP on added and modified units (missing coverage still counts as 0%).
- Data-model view is a **second diagram**, not more boxes on the class map (see below).

Most PRs should look **boring** on the map. Drift is interesting PRs that nobody mapped.

### 4. Data model / schema (second view)

State topology is not behavior topology. Generate as-built from what is in the tree (start with obvious declared models: e.g. Django/`SQLAlchemy` style classes, Prisma/`*.prisma`, raw SQL migrations as a later increment). Optional policy for which package may own which tables. A PR that adds a table and a writer in the wrong context lights up **both** views.

### 5. Honest unit diffs (still required)

v1 lies about same-signature body rewrites. A member or function is `modified` if signature, modifiers, optional, decorators, **complexity**, or **body hash** changed. CRAP runs on added and modified units. Boxes are keyed by `path::name`. Changed free functions appear on the diagram. TypeScript imports are extracted like Python’s.

### 6. Where the picture appears

Distribution is [ADR 0002](0002-cli-ci-skill.md): CLI kernel, sticky PR comment as the reviewer surface, project skill as the author/agent trigger. Artifacts alone are not review.

### Review order the report must encode

1. New policy violations (illegal edges, wrong-package types, layer-crossing cycles)
2. Breaking public signature / heritage / schema changes
3. High CRAP on added **and body-modified** units
4. New coupling that is legal but worth seeing
5. Untested new types (symbol mentioned in a test file in this PR)
6. Everything else

### Quality gate vs picture

Do **not** fail CI on CRAP thresholds. That is craft, not architecture.

**Do** allow an opt-in `--fail-on-violation` (and the GitHub Action equivalent) so a new illegal edge can fail the check. Default off until a repo has a policy. Visibility first; throttle when the architect asks.

### Explicitly out of scope

- Becoming uml-viewer: live window, companion agent loop, what-if proposal canvas, mutation-testing IDE.
- Secrets, CVEs, feature-correctness, style nits.
- Sequence diagrams, commit animation, rainbow dashboards.
- Rename matching, MCP server, marketplace Action, auto-ingest of coverage.py/Istanbul (still later).
- Hand-maintained UML in `docs/` as the architecture. Renders are optional; **code + policy** are the source of truth.

## Consequences

### Positive

- The tagline becomes true for an architect: he or she can see whether the change belonged, not only that a class appeared.
- Agent slop that “looks fine in the hunks” shows up as a red edge or a type in the wrong package.
- Bob’s split is preserved: generated as-built, authored policy, no invented layers.
- The examined repo’s owner chooses gitignore vs check-in for generated files; policy is what he or she should commit.

### Negative / trade-offs

- Whole-tree extract is slower than changed-files-only. Snapshot caching and “neighborhood of the delta” display keep CI and PR comments usable.
- A repo with no package structure gets a hairball. Hierarchy (package boxes first, types on drill or in the delta) is mandatory; dumping every class on the PR is a failure of the product.
- Body hashes flag comment-only edits as `modified`. Accept that; the line diff is where noise is dismissed.
- Schema extractors will be incomplete at first. Ship code topology overlay before a perfect ER story.
- `--fail-on-violation` can be noisy if the policy is wrong. That is a policy bug, not a reason to skip the map.

## Alternatives considered

- **Keep v1 (changed-files signature delta).** Fast. Does not reduce architecture drift.
- **Check in a hand-drawn `docs/architecture` UML.** Rots. Becomes a second lie. Rejected.
- **Live full-repo UML as the only review (uml-viewer).** Right for Bob in a local loop. Wrong for GitHub PR reviewers who will never open that window.
- **Parse whole tree but no policy.** A map without a rule does not throttle slop.
- **Merge-gate CRAP.** Punishes complexity, not placement. Rejected.

## Follow-up

One implementation sequence: [docs/plan.md](../plan.md).
