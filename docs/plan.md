# Plan: implement Skyline (map, policy, overlay)

This is the **only** implementation plan. It makes [ADR 0001](adr/0001-map-policy-overlay.md), [ADR 0002](adr/0002-cli-ci-skill.md), and [ADR 0003](adr/0003-json-export-and-prompt-bundling.md) true.

It folds the unimplemented 2026-09-20 “PR review signals” plan (body-delta, qualname boxes, coupling, review chips, PR comment, skill) plus the architecture-drift vision (snapshot, policy, overlay, data-model view).

Work in this order. Each step lands with tests. Later steps assume earlier ones. Do not start a parallel plan.

## Non-goals (do not pull into this plan)

- Live uml-viewer clone (companion agent window, what-if canvas, mutation IDE)
- MCP, VS Code extension, GUI, marketplace Action
- Auto-ingest of coverage.py / Istanbul (missing coverage stays 0%)
- Rename matching, Python instance-attribute extraction, TypeScript `type` / `enum` / namespaces
- Merge-gating CRAP

## v1 already true (do not rebuild)

- Three-dot `base...head` git range, changed `.py` / `.ts` / `.tsx` extracted into `ModuleModel`
- Type/member/function **signature** and heritage diff
- CRAP on added/modified units when status is already `modified`
- HTML + SVG report, demo samples, CI artifact upload from checkout

## 1. Honest unit diffs (body, complexity, decorators)

**Why.** Same-signature rewrites are invisible; CRAP never runs on those units. Highest-leverage lie in v1.

**Code**

- Add `body_hash: Optional[str]` to `Member` and `FunctionEntity` in [`skyline/model.py`](../skyline/model.py).
- Python: hash `ast.unparse` of the unit’s own body (not nested defs) in [`skyline/python_extractor.py`](../skyline/python_extractor.py). Set `exported` from the public-name heuristic (leading `_` is internal; dunder methods such as `__init__` stay public).
- TypeScript: hash `node.body.getText()` in [`skyline/ts_extractor/extract.js`](../skyline/ts_extractor/extract.js); thread it through [`skyline/ts_client.py`](../skyline/ts_client.py).
- In [`skyline/diff.py`](../skyline/diff.py): if complexity differs, reason includes `complexity X → Y`; elif `body_hash` differs, `body changed`. Either makes status `modified`.
- Class decorator list changes are a type-level modification (already extracted, never diffed).
- [`skyline/crap.py`](../skyline/crap.py) `annotate` already scores added/modified: no change once status is right.

**Tests**

- Same signature, complexity `2 → 18` → `modified`, CRAP present.
- Same signature and complexity, different body hash → `modified`, reason `body changed`, CRAP present.
- Identical body → `unchanged`, no CRAP.

## 2. Diagram identity: qualname keys and function boxes

**Why.** Two `Client` classes collide (`boxes[t.name]`). Python-heavy PRs can have an empty UML.

**Code**: [`skyline/render_svg.py`](../skyline/render_svg.py)

- Key boxes by `qualname` (`path::name`). Title stays the short name; show path when short names collide.
- Resolve `extends` / `implements` by short name: prefer same-file, else any primary, else `external::{name}`.
- Draw changed module-level functions as `«function»` boxes.

**Tests**

- Two modified classes with the same name in different files both appear.
- A changed free function appears in the SVG.

## 3. Coupling: extract and resolve imports

**Why.** Python stores `imports` and nothing uses that list. TypeScript emits `imports: []`.

**Code**

- Extract TS `import` / `export from` specifiers in `extract.js`; copy onto `ModuleModel.imports`.
- Resolve to files: relative TS paths; Python `a.b` ↔ `a/b.py`. Drop unresolved third-party modules from the diagram (omit those from the coupling view).
- `ImportChange` on `ModelDiff`. Status added / removed / unchanged. Two-cycles thicker.

After step 4 this resolver runs against the **full** as-built file set, not only files in the three-dot name list. In this step, wire it on whatever modules were extracted so tests can land.

**Tests**

- Python `from pkg.b import x` resolving to `pkg/b.py` is an added import when new.
- TS `import { x } from './b'` similarly.
- `import react` does not appear.

## 4. Snapshot: as-built map of a whole ref

**Why.** The city map. Git has the tree; Skyline must parse it.

**Code**

- `skyline snapshot --repo . --ref HEAD --out-dir .skyline` (override `--out-dir docs/architecture`).
- Walk all `.py` / `.ts` / `.tsx` at that ref (gitignore-aware via `git ls-files` at the ref, still restricted by `--lang`).
- Write `model.json` (versioned IR of `{path: ModuleModel}`). Optional `--render` writes Mermaid and/or SVG. Never require hand-edits to `model.json`.
- Document that the examined repo’s owner chooses gitignore vs check-in. Do not silently gitignore for him or her.
- `skyline diff` may load `.skyline/model.json` for base if `--ref` matches and the file exists; otherwise extract.

**Tests**

- Snapshot of a fixture tree includes an unchanged file that `diff --name-only` would omit.
- Round-trip: extract → json → load equals the in-memory model.

## 5. Policy: as-intended layers and allowed edges

**Why.** A map without a rule does not throttle slop. Pictures without a rule rot.

**Code**

- Read `skyline.policy.toml` from the examined repo root (path override `--policy`).
- Schema: `layers` (ordered inner→outer or explicit ranks), `allow` / default “downward only”, `omit` path prefixes, optional `proposals` (named groupings labeled not-in-code).
- Map each file path to a layer by longest-prefix match. Unmapped files are unranked (no violation).
- Missing policy file: no violations, overlay still works.
- Do not invent layer names that match no path prefix.

**Tests**

- `domain/` → `infra/` is violating when policy says domain is inner.
- Same-rank import is not violating.
- No policy file → zero violations.

## 6. Overlay: paint the PR on the map, report violations

**Why.** This is the architect’s product. Delta-only islands are not “how a change shapes the design.”

**Code**

- `skyline diff` extracts (or loads) **full** models at base and head.
- Display default: changed types/functions + neighborhood (heritage and new/removed import ends), not the entire hairball.
- Package/layer boxes when policy exists; types inside the delta.
- List **violations** first in HTML: new illegal edges, new types whose path is in the wrong layer relative to what those types import, new layer-crossing cycles.
- `--fail-on-violation` exits 1 if any new violation exists. Default 0.
- Hierarchical layout: parents / inner layers above or below children per UML convention already used for arrows; do not wrap-row the overlay if layers exist.

**Tests**

- Unchanged file in the neighborhood of a new subclass appears as external/neighborhood, not omitted.
- New `domain` → `infra` import is a violation with policy; the same import is only a coupling edge without policy.
- `--fail-on-violation` exit code.

## 7. Data-model view (second diagram)

**Why.** Schema drift is architecture. Do not mix ER and class UML on one canvas.

**Code**

- First increment: extract declared models that are cheap and real: Django `models.Model` subclasses and SQLAlchemy `Column` / `Mapped` tables from Python; Prisma `model` blocks from `*.prisma` if present.
- Diff tables/columns/relations the same added/removed/modified way.
- Second SVG/section in the HTML report. Policy optional: `data.owners` package → table prefix.
- SQL migration parsers are a follow-on if this increment ships; do not block steps 8-10 on perfect SQL.

**Tests**

- Added column on a Django model shows as modified table, not only a Python class member, in the data-model section.
- Class diagram does not duplicate every column as if it were the ER view’s job (members may still appear on the class).

## 8. Review signals on the report

**Why.** Do not hunt badges. Encode ADR 0001’s review order.

**Code**: new [`skyline/review.py`](../skyline/review.py)

- Churn caption from base/head source maps.
- Breaking: public + (removed or non-body-only signature/heritage/schema change).
- Tests-in-PR: test path glob; name appears in a changed test file at head.
- Risk ranking: top N CRAP on added/modified units.
- HTML: violations, caption, risk strip, overlay UML, coupling, data-model, details with chips.

**Tests** for caption, breaking vs body-only, test-file pairing.

## 9. Put the overlay on the PR

**Why.** Artifacts are not review (ADR 0002).

**Code**

- [`skyline/render_markdown.py`](../skyline/render_markdown.py): `<!-- skyline-report -->`, violations, caption, stats, risk list, Mermaid class overlay (lossy), coupling flowchart, data-model mermaid if any.
- CLI `--comment skyline_comment.md`.
- [`.github/workflows/skyline.yml`](../.github/workflows/skyline.yml): `pull-requests: write`, `pip install .`, HTML + comment, sticky `actions/github-script` update-or-create, keep the HTML artifact.

**Tests:** markdown contains the marker and a violation heading when one exists.

## 10. Project skill (trigger, not analyzer)

**Why.** Authors and agents need the same CLI before push.

**Code**: `.cursor/skills/skyline/SKILL.md`

- Triggers: review this PR, snapshot the architecture, check design/risk before opening a PR.
- Run `skyline snapshot` / `skyline diff … --comment …` from this checkout.
- Report in ADR 0001 review order. Do not skip the CLI.

## 11. JSON export and prompt bundling

**Why.** The skill hands the structural model to an agent. [ADR 0003](adr/0003-json-export-and-prompt-bundling.md): `--format json` and `--emit-prompt` are separate flags. The prompt is a file the repo can replace, like `skyline.policy.toml`.

**Code**

- [`skyline/render_json.py`](../skyline/render_json.py): same diff the HTML report uses. Full CRAP list, not the top-five summary.
- CLI `--format {html,json}`. The flag chooses the renderer. The `--out` extension does not.
- [`skyline/prompts/review.md`](../skyline/prompts/review.md): default template. One `{{SKYLINE_DATA}}` marker.
- [`skyline/render_prompt.py`](../skyline/render_prompt.py): always builds the JSON, substitutes the template, fails if the marker is missing.
- CLI `--emit-prompt out.md` and `--prompt-template path.md`. Works without `--format` or `--out`.

**Not in this step.** No workflow change. No new violation rules.

## Suggested notes while in the files anyway

- Hierarchical layout in step 2 is welcome if cheap; required in step 6 when layers exist.
- Coverage map (`--coverage`) stays manual JSON.

## Done when

- A same-signature body rewrite is `modified` and scored.
- Two `Client` types in different files both render; free functions render.
- TS and Python import edges among resolved files show; `react` does not.
- `skyline snapshot` writes a whole-ref IR including files the three-dot diff would skip.
- With `skyline.policy.toml`, a new inner→outer import is a violation, listed first, and can fail CI via `--fail-on-violation`.
- Without a policy, the same PR still overlays on the as-built neighborhood.
- A Django/Prisma-style schema change appears in a second view.
- The GitHub PR has a sticky bot comment with Mermaid overlay + violations; a project skill only invokes that CLI.
- Tests cover body-delta, qualname boxes, resolved imports, snapshot round-trip, and policy violations.
