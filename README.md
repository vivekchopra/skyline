# skyline

Skyline makes architecture drift visible, one PR at a time: what changed, structurally, and how risky it is.

AI-generated code means more PRs, and bigger ones, and human review of code (as done in the days of artisanal coding) doesn't scale. Reviews need to move one layer up: to the architecture level.

AI systems are good at producing locally reasonable changes, but they don't naturally preserve long-term consistency across an entire system. Over time, this creates "architecture slop": a codebase where each individual change may make sense in isolation but the overall structure gradually loses coherence.

Skyline diffs a PR structurally instead of textually: classes and interfaces added, removed, or changed, what they now extend or implement, and a CRAP score on anything complex and new. Point it at a base and head ref and it draws the diagram of that change on the as-built map of the whole tree. Give it a layering policy and it flags what breaks it: a new class in the wrong package, a dependency pointing the wrong way.

```
pip install skyline-review
skyline diff --repo . --base main --head my-feature-branch
```

The report is written to `skyline_report.html`. Green indicates what was added, red removed, orange modified, and dashed grey any unchanged type referenced (a base class or interface, say) so you can see where the change plugs into the existing hierarchy. Inheritance (`extends`) draws as a solid arrow; interface realization (`implements`) draws dashed, per UML convention. Each added or modified method also gets a CRAP score, colored low to severe, so you can see which new code is actually risky. When a `skyline.policy.toml` is present, new policy violations are listed above the diagram.

Python and TypeScript files in the same PR are diffed together automatically, no extra flag needed. Restrict to one language with `--lang python` or `--lang typescript` if that's what you want.

```
skyline demo --lang python
skyline demo --lang typescript
```

## Credit

The CRAP score, and the idea of overlaying a risk score directly on a structural diagram, is influence by Robert C. Martin's (unclebob's) **[uml-viewer](https://github.com/unclebob/uml-viewer)** and **[crap4clj](https://github.com/unclebob/crap4clj)**, which do this for Clojure codebases with considerably more sophistication (he also integrates mutation-testing scores, live-update from a running companion agent, and paints an actual navigable UML diagram rather than a diff view). Skyline borrows the formula and the "missing coverage counts as the worst case, not unknown" philosophy from his README. It is not affiliated with that project in any form, and if you're working in Clojure and want the full picture (a live map of the whole repo, not a PR overlay), use his tools directly!

## Why not just read the diff?

A textual diff shows *lines*. It doesn't answer the questions a developer or an architect actually has:

- Did this PR add a type, or change what a class extends?
- Did a public signature change in a way that breaks callers?
- Is the "200 line diff" one new class, or five unrelated shapes?
- Did new code land in the wrong layer, or import the forbidden direction?
- How risky is the new behavior (complexity times missing tests)?

Agents don't share an architect's sense of where code belongs. Skyline's job is to make that mismatch visible on the merge path.

## What it does today (v1)

- **Python**: classes, methods, module-level functions, base classes, via the standard-library `ast` module. The extractor has no third-party dependencies. Reading a policy file uses `tomllib` on Python 3.11+ and `tomli` on older Pythons.
- **TypeScript / TSX**: classes, interfaces, methods, properties, module-level functions (including exported arrow functions), decorators, `extends` vs `implements`, via the real TypeScript compiler API (not regex), so generics, decorators, overloads, and modern syntax parse correctly. See [TypeScript support](#typescript-support) below.
- **Type and member diff**: added, removed, modified, with per-member signature diffs (params, modifiers, return type). A same-signature rewrite is also modified when complexity or the body hash changes. A class decorator change is a type-level modification.
- **Relationship-change detection**: flags when a type starts or stops extending or implementing something.
- **Imports**: Python and TypeScript import edges resolved to files in the tree. Unresolved third-party modules (such as `react`) are dropped. A two-way import is drawn thicker.
- **As-built map**: `skyline snapshot` parses every matching source file at a git ref, not only the names in the three-dot diff, and writes `.skyline/model.json`. That JSON is generated. Code plus policy are the source of truth. In a repo you are reviewing, gitignore `.skyline/`. Check `model.json` in only when you want that snapshot in the pull request as a lockfile.
- **Policy**: a checked-in `skyline.policy.toml` names layers that already exist as path prefixes, and which way dependencies may point. A new inner-to-outer import is a violation. No policy file means the overlay still runs and nothing is painted illegal. `--fail-on-violation` can fail the run. CRAP never does.
- **PR overlay**: the default picture is the delta plus its neighborhood (the base class a changed type extends, the other end of a new import), not every box in the repo. With a policy, types sit in layer bands, inner above outer. Violations come first: new illegal edges, new types in the wrong package, new cycles that cross layers.
- **Data model**: a second diagram for Django `models.Model` subclasses, SQLAlchemy `Column` / `mapped_column` tables, and Prisma `model` blocks. An added column shows up there. It is not copied onto the class diagram as if the class map were an ER diagram. SQL migration files aren't parsed yet.
- **CRAP score**: every added or modified method and function gets a Change-Risk-Anti-Pattern score (`complexity² × (1 − coverage)³ + complexity`), computed from real cyclomatic complexity for both languages. See [CRAP scoring](#crap-scoring) below.
- **Visual diagram**: SVG UML-style boxes, colored by change type, with `extends` drawn as a solid arrow and `implements` dashed, per UML convention, plus a colored CRAP badge on each risky box, embedded directly in the HTML report. Boxes are keyed by path and name, so two classes with the same short name both appear, and a changed module-level function is drawn as `«function»`. No Graphviz, no system rendering dependencies.
- **Mixed-language PRs**: Python and TypeScript changes in the same PR are analyzed and diffed together in one report. `.prisma` files are included for the data-model view.
- **Where you see it**: the HTML report is the full diagram. `skyline diff --comment skyline_comment.md` writes the lossy markdown a reviewer can read in the PR thread (violations, review order, Mermaid). The workflow in this repo posts one sticky comment and still uploads the HTML artifact. The project skill at `.cursor/skills/skyline/SKILL.md` only tells an agent when to run that CLI.

## CRAP scoring

Every **added or modified** method or function gets scored:

```
CRAP = complexity² × (1 − coverage)³ + complexity
```

- **Complexity** is real cyclomatic complexity, computed by walking each method or function's own AST (Python `ast`, or the TypeScript compiler API) and counting decision points (`if`, loops, `catch`, ternaries, `&&`/`||`/`??`, `switch` cases, comprehensions). It doesn't descend into nested function definitions, so each unit's score stays scoped to itself.
- **Coverage** defaults to **0% for everything** unless you supply a coverage map (`--coverage path.json`). That's deliberate, not a placeholder: an untested method shouldn't look safer than a tested one just because skyline wasn't told about it. (This convention, and the formula itself, are inspired by uml-viewer/crap4clj, see [Credit](#credit) above.)
- Score bands: **low** (≤5, green), **moderate** (≤10, yellow), **high** (≤30, orange), **severe** (>30, red). The 30-point "risky" cutoff follows CRAP4J's original published guidance; the low/moderate split is skyline's own.
- Removed and unchanged methods aren't scored. A PR review tool cares about the risk of what's being introduced, not what's already there or what's leaving. A body rewrite with the same signature is modified, so it is scored.

### Coverage input

By default no coverage data is used, so everything scores as 0% covered, which is the honest worst case for a quick PR check. To supply real coverage, pass `--coverage path/to/map.json`, a flat JSON object mapping a member's qualified name to a coverage fraction (0-1):

```json
{
  "src/payments.py::PaymentProcessor.charge": 0.92,
  "src/payments.py::validate_amount": 1.0,
  "src/payments.ts::PaymentProcessor.send": 0.4
}
```

Keys are `"<file path>::<ClassName>.<memberName>"` for class or interface members, or `"<file path>::<functionName>"` for module-level functions, the same paths and names shown in the report itself. Generating this map automatically from `coverage.py` or `nyc`/`istanbul` output isn't built in yet (see [Roadmap](#roadmap)); for now it's a manual or scripted step. Entries not found in the map are scored at 0% coverage.

## TypeScript support

TypeScript parsing shells out to a small bundled Node.js script that uses the actual `typescript` npm package's compiler API, the same parser `tsc` uses, rather than a hand-rolled regex parser, which would break on anything beyond trivial syntax (generics, decorators, overloads, arrow functions as class fields, JSX, and so on).

Requirements: **Node.js 18+** and **npm** on `PATH`. `pip install skyline-review` itself stays dependency-free for the TypeScript compiler; the first time you analyze a `.ts`/`.tsx` file, skyline runs `npm install typescript` once into `~/.cache/skyline/ts_extractor/` (a few seconds, one-time). Delete that directory to force a clean reinstall, for example after a skyline upgrade.

Known limitations for TypeScript:
- Type resolution isn't performed (this is a syntax-only parse of each file, not a full program compile), so a method signature diff compares the type text as written, not resolved or aliased types.
- TypeScript's constructor-parameter-property shorthand (`constructor(private x: Type)`) is captured as a constructor parameter, not also as a separate class property member.
- `type` aliases and `enum` declarations aren't extracted yet (classes and interfaces are).

## What v1 doesn't do yet

Skyline isn't a live uml-viewer clone (no companion-agent window, no what-if canvas). It's the PR-shaped version of that idea: overlay on the pull request, where review already happens.

It doesn't auto-ingest coverage.py or Istanbul output (missing coverage stays 0%), match renames, extract Python instance attributes, or extract TypeScript `type` / `enum` / namespaces. It doesn't parse SQL migrations. It doesn't fail CI on a CRAP threshold. It isn't an MCP server, an editor extension, or a marketplace Action.

## Usage

```
skyline diff --repo <path> --base <ref> --head <ref> [--out report.html] [--comment skyline_comment.md] [--lang python typescript] [--coverage map.json] [--policy skyline.policy.toml] [--fail-on-violation]
skyline snapshot --repo <path> --ref HEAD [--out-dir .skyline] [--render]
```

- `--repo`: path to the git repository (default: current directory)
- `--base`: the PR's target branch, e.g. `main`, `origin/main`
- `--head`: the PR's branch, e.g. `HEAD`, a branch name, a commit SHA. A branch that is not checked out locally, but exists on exactly one remote, is read from that remote-tracking ref (`origin/my-feature-branch`). If several remotes have it, pass the remote-tracking name.
- `--out`: output HTML file path (default: `skyline_report.html`)
- `--comment`: also write the markdown PR comment
- `--lang`: one or more of `python`, `typescript` (default: both, whichever files are present). `.prisma` files are read either way
- `--coverage`: optional path to a coverage map JSON file (see [Coverage input](#coverage-input)); without it, every method or function is scored assuming 0% coverage
- `--policy`: path to `skyline.policy.toml` (default: `<repo>/skyline.policy.toml`). A missing file draws no illegal edges
- `--fail-on-violation`: exit 1 when this change introduces a policy violation. Off unless you pass it. Does not fail on CRAP
- `--snapshot-dir`: where a previous `model.json` lives (default: `.skyline`). `diff` uses it when the ref matches, and extracts otherwise
- `snapshot --ref`: git ref to map (default: `HEAD`)
- `snapshot --out-dir`: output directory (default: `.skyline`; `docs/architecture` if you want the render under `docs/`)
- `snapshot --render`: also write `map.md` and `map.svg`. The JSON model stays the IR

`diff` writes `skyline_report.html` in the current directory. It also stores each commit's map in `.skyline/maps/<sha>.json`. The sha is the checksum: the same commit prints `No change in <ref>; loading previous run` and skips the read. `snapshot` writes `.skyline/model.json` inside the repo, plus `map.md` and `map.svg` when you pass `--render`. Skyline does not add these to `.gitignore`. In a repo you are reviewing, ignore them:

```gitignore
.skyline/
skyline_report.html
```

Commit `.skyline/model.json` only when you want that snapshot to show up in the pull request as a lockfile. `skyline.policy.toml` stays committed either way.

Internally `diff` still uses git's three-dot range (`base...head`) for what counts as the PR, the same range GitHub shows, so the overlay is what the PR introduced relative to its merge-base, not unrelated drift on `main`. The maps underneath that overlay are the whole tree at each ref.

### Policy

Optional. This is a violation when `domain/` is inner and `infra/` is outer:

```toml
layers = ["domain", "app", "infra"]
```

Same-rank imports are allowed unless you set `same_rank = false`. An explicit exception looks like `allow = ["domain -> app"]`. `omit` is a list of path prefixes to skip. `[proposals]` names a grouping that isn't a package yet; it is labeled, not instantiated, and it isn't a layer. `[data.owners]` can say which package prefix owns which table names.

## How it works

1. At `--base` and at `--head`, list tracked `.py`, `.ts`, `.tsx`, and `.prisma` files (`git ls-tree`) and read them with `git show`, without touching the working tree. If `.skyline/model.json` was generated for that same ref, load it instead of extracting again.
2. Parse both trees into one language-agnostic model: Python via `ast`, TypeScript via the TypeScript compiler API (see [TypeScript support](#typescript-support)), Prisma `model` blocks via a small scanner. All of them produce `ModuleModel` (types, members, functions, imports, tables).
3. Diff the two models: signatures, heritage, decorators, complexity, body hash, resolved imports, and declared tables.
4. If `skyline.policy.toml` is present, mark new illegal edges, new types sitting in the wrong layer for what they import, and new cycles that cross layers.
5. Render the neighborhood, not the whole hairball: an SVG (boxes sized to their content, colored by change status, solid arrows for `extends` and dashed for `implements`, layer bands when a policy exists), wrapped in an HTML page whose order is violations, churn, CRAP risk, the overlay, coupling, the data-model diagram, then the text breakdown. `--comment` writes the same order as Mermaid.

## Using it in CI

See `.github/workflows/skyline.yml`. On every PR update it installs skyline from the checkout (`pip install .`), writes the HTML report, uploads that artifact, and posts or updates one sticky comment (`<!-- skyline-report -->`) with the overlay and any policy violations ([ADR 0002](docs/adr/0002-cli-ci-skill.md)). The comment is the reviewer surface. The artifact is the full SVG. Add `--fail-on-violation` in that workflow when a repo has a policy and a new illegal edge should fail the check.

## Development

Decisions: [docs/adr](docs/adr/README.md). The implementation sequence those decisions required is [docs/plan.md](docs/plan.md).

```
git clone https://github.com/vivekchopra/skyline
cd skyline
pip install -e ".[dev]"
pytest
```

The codebase is small and split by concern:

| File | Responsibility |
| --- | --- |
| `skyline/model.py` | Shared dataclasses (`ModuleModel`, `TypeEntity`, `Member`, `FunctionEntity`, `Table`) |
| `skyline/python_extractor.py` | Python source to model (`ast`, complexity, body hash, Django and SQLAlchemy tables) |
| `skyline/prisma_extractor.py` | Prisma `model` blocks to tables |
| `skyline/ts_extractor/extract.js` | TypeScript source to JSON (compiler API, complexity, body hash, imports) |
| `skyline/ts_client.py` | Bootstraps the Node tooling, shells out, parses JSON to model |
| `skyline/languages.py` | Routes files to the right extractor by extension |
| `skyline/git_utils.py` | Changed paths, and the file list at a ref |
| `skyline/imports.py` | Resolve import specifiers to files in the tree; drop third-party modules |
| `skyline/diff.py` | Diff two structural models (language-agnostic) |
| `skyline/policy.py` | Load `skyline.policy.toml` and list violations |
| `skyline/snapshot.py` | Write and reload `.skyline/model.json` |
| `skyline/serialize.py` | Versioned JSON for that model |
| `skyline/crap.py` | CRAP scoring and coverage-map loading (see [Credit](#credit)) |
| `skyline/review.py` | ADR 0001 review order: violations, breaking changes, CRAP, coupling, untested types |
| `skyline/render_svg.py` | Overlay and data-model SVG |
| `skyline/render_html.py` | Those diagrams plus the text report |
| `skyline/render_mermaid.py` | Lossy Mermaid for the PR comment and `snapshot --render` |
| `skyline/render_markdown.py` | Sticky-comment markdown |
| `skyline/cli.py` | `skyline diff`, `skyline snapshot`, `skyline demo` |

Adding a language means writing one more extractor that produces `model.ModuleModel` objects and wiring it into `languages.py`. The diff engine and the renderers need no changes for that.

## Roadmap

Off this plan, later: auto-ingested coverage maps, mutation scores, more languages, TypeScript `type` / `enum` / namespaces, rename matching, SQL migration parsers, and a reusable marketplace Action once the in-repo comment path has been used for real.

## License

MIT. See `LICENSE`.
