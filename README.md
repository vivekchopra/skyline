# skyline

Skyline makes architecture drift visible, one PR at a time: what changed, structurally, and how risky it is.

AI-generated code means more PRs, and bigger ones. You can review a person's 600-line diff line by line because there's reasoning behind it to follow. An agent's diff doesn't have that. It just looks plausible, hunk by hunk, whether or not it belongs where it landed.

The question that matters for a PR like that isn't "is this line correct," it's "does this type belong here, and what does it now depend on." Answering that by staring at a diff and reconstructing the class diagram in your head doesn't scale.

Skyline diffs a PR structurally instead of textually: classes and interfaces added, removed, or changed, what they now extend or implement, and a CRAP score on anything complex and new. Point it at a base and head ref and it draws the diagram. Give it a layering policy and it flags what breaks it, a new class in the wrong package, a dependency pointing the wrong way.

```
pip install skyline
skyline diff --repo . --base main --head my-feature-branch
```

Opens as `skyline_report.html`. Green is added, red is removed, orange
is modified, dashed grey is an unchanged type referenced (for example a
base class or interface) so you can see where the change plugs into the
existing hierarchy. Inheritance (`extends`) draws as a solid arrow;
interface realization (`implements`) draws dashed, per UML convention.
Each added or modified method also gets a CRAP score, colored
low to severe, so you can see which new code is actually risky.

Python and TypeScript files in the same PR are diffed together
automatically. No extra flag. Restrict to one language with
`--lang python` or `--lang typescript` if you want.

Try it without a git repo, on bundled sample code:

```
skyline demo --lang python
skyline demo --lang typescript
```

## Credit

The CRAP score, and the idea of overlaying a risk score directly on a
structural diagram, are directly inspired by Robert C. Martin's
(unclebob's) **[uml-viewer](https://github.com/unclebob/uml-viewer)** and
**[crap4clj](https://github.com/unclebob/crap4clj)**, which do this for
Clojure codebases with considerably more sophistication (he also
integrates mutation-testing scores, live-update from a running companion
agent, and paints an actual navigable UML diagram rather than a diff
view). `skyline` borrows the formula and the "missing coverage counts as
the worst case, not unknown" philosophy from his README. It is an
independent, unaffiliated project. If you are working in Clojure and
want the full picture (a live map of the whole repo, not a PR overlay),
use his tools directly.

## Why not just read the diff?

A textual diff shows *lines*. It does not answer the questions a developer
or an architect actually has:

- Did this PR add a type, or quietly change what a class extends?
- Did a public signature change in a way that breaks callers?
- Is the "200 line diff" one new class, or five unrelated shapes?
- Did new code land in the wrong layer, or import the forbidden direction?
- How risky is the new behavior (complexity times missing tests)?

Agents do not share an architect's sense of where code belongs. Skyline's
job is to make that mismatch visible on the merge path.

## What it does today (v1)

- **Python**: classes, methods, module-level functions, base classes,
  via the standard-library `ast` module. Zero dependencies.
- **TypeScript / TSX**: classes, interfaces, methods, properties,
  module-level functions (including exported arrow functions), decorators,
  `extends` vs `implements`, via the real TypeScript compiler API (not
  regex), so generics, decorators, overloads, and modern syntax parse
  correctly. See [TypeScript support](#typescript-support) below.
- **Type and member diff**: added / removed / modified, with per-member
  signature diffs (params, modifiers, return type).
- **Relationship-change detection**: flags when a type starts or stops
  extending or implementing something.
- **CRAP score**: every added or modified method and function gets a
  Change-Risk-Anti-Pattern score (`complexity² × (1 − coverage)³ + complexity`),
  computed from real cyclomatic complexity for both languages. See
  [CRAP scoring](#crap-scoring) below.
- **Visual diagram**: SVG UML-style boxes, colored by change type, with
  `extends` drawn as a solid arrow and `implements` dashed, per UML
  convention, plus a colored CRAP badge on each risky box, embedded
  directly in the HTML report. No Graphviz. No system rendering
  dependencies.
- **Mixed-language PRs**: Python and TypeScript changes in the same PR are
  analyzed and diffed together in one report.

## CRAP scoring

Every **added or modified** method/function gets scored:

```
CRAP = complexity² × (1 − coverage)³ + complexity
```

- **Complexity** is real cyclomatic complexity, computed by walking each
  method/function's own AST (Python `ast`, or the TypeScript compiler
  API) and counting decision points (`if`, loops, `catch`, ternaries,
  `&&`/`||`/`??`, `switch` cases, comprehensions). It does not descend
  into nested function definitions. Each unit's score stays scoped to
  itself.
- **Coverage** defaults to **0% for everything** unless you supply a
  coverage map (`--coverage path.json`). See below. This is deliberate,
  not a placeholder: an untested method should not look safer than a
  tested one just because skyline was not told about it. (This convention,
  and the formula itself, are inspired by uml-viewer/crap4clj. See
  [Credit](#credit).)
- Score bands: **low** (≤5, green), **moderate** (≤10, yellow), **high**
  (≤30, orange), **severe** (>30, red). The 30-point "risky" cutoff
  follows CRAP4J's original published guidance; the low/moderate split is
  skyline's own.
- Removed and unchanged methods are not scored. A PR review tool cares
  about the risk of what is being introduced, not what is already there
  or what is leaving.

### Coverage input

By default no coverage data is used (everything scores as 0% covered,
which is the honest worst case for a quick PR check). To supply real
coverage, pass `--coverage path/to/map.json`, a flat JSON object mapping
a member's qualified name to a coverage fraction (0-1):

```json
{
  "src/payments.py::PaymentProcessor.charge": 0.92,
  "src/payments.py::validate_amount": 1.0,
  "src/payments.ts::PaymentProcessor.send": 0.4
}
```

Keys are `"<file path>::<ClassName>.<memberName>"` for class/interface
members, or `"<file path>::<functionName>"` for module-level functions,
the same paths and names shown in the report itself. Generating this map
automatically from `coverage.py` / `nyc`/`istanbul` output is not built in
yet (see [Roadmap](#roadmap)); for now it is a manual or scripted step.
Entries not found in the map are scored at 0% coverage.

## TypeScript support

TypeScript parsing shells out to a small bundled Node.js script that uses
the actual `typescript` npm package's compiler API, the same parser
`tsc` uses, rather than a hand-rolled regex parser, which would break on
anything beyond trivial syntax (generics, decorators, overloads, arrow
functions as class fields, JSX, and so on).

Requirements: **Node.js 18+** and **npm** on `PATH`. `pip install skyline`
itself stays dependency-free; the first time you analyze a `.ts`/`.tsx`
file, skyline runs `npm install typescript` once into
`~/.cache/skyline/ts_extractor/` (a few seconds, one-time). Delete that
directory to force a clean reinstall (for example after a skyline upgrade).

Known v1 limitations for TypeScript:
- Type resolution is not performed (this is a syntax-only parse of each
  changed file in isolation, not a full program compile), so a method
  signature diff compares the type text as written, not resolved or aliased
  types.
- TypeScript's constructor-parameter-property shorthand (`constructor(private x: Type)`)
  is captured as a constructor parameter, not also as a separate class
  property member.
- `type` aliases and `enum` declarations are not extracted yet (classes and
  interfaces are).

## What v1 does not do yet

v1 is a structural delta of **changed files**, not yet the full map. It
does not yet snapshot the whole tree, load a `skyline.policy.toml`, fail
on a new illegal edge, extract a data-model view, or post a sticky PR
comment. Those are specified in [ADR 0001](docs/adr/0001-map-policy-overlay.md)
and sequenced in [docs/plan.md](docs/plan.md).

Skyline is not a live uml-viewer clone (no companion-agent window, no
what-if canvas). It is the PR-shaped version of that idea: overlay on the
pull request, where review already happens.

## Usage

```
skyline diff --repo <path> --base <ref> --head <ref> [--out report.html] [--lang python typescript] [--coverage map.json]
```

- `--repo`: path to the git repository (default: current directory)
- `--base`: the PR's target branch, e.g. `main`, `origin/main`
- `--head`: the PR's branch, e.g. `HEAD`, a branch name, a commit SHA
- `--out`: output HTML file path (default: `skyline_report.html`)
- `--lang`: one or more of `python`, `typescript` (default: both, i.e.
  whichever changed files are present)
- `--coverage`: optional path to a coverage map JSON file (see
  [Coverage input](#coverage-input)); without it, every method/function is
  scored assuming 0% coverage

Internally this uses git's three-dot diff (`base...head`), the same range
GitHub shows for a pull request, so the overlay is what the PR
introduced relative to its merge-base, not unrelated drift on `main`.

v1 only *parses* files that changed, which keeps large repos fast and
also hides the rest of the map around the delta. Whole-tree snapshot and a
neighborhood overlay are in [docs/plan.md](docs/plan.md).

## How it works

1. `git diff --name-only base...head -- '*.py' '*.ts' '*.tsx'`: find
   changed source files.
2. For each changed file, `git show ref:path`: read its content at both
   refs without touching your working tree.
3. Parse both versions into a shared, language-agnostic model: Python via
   the standard-library `ast` module; TypeScript via the real TypeScript
   compiler API (see [TypeScript support](#typescript-support)). Both
   produce the same `ModuleModel` shape (types, members, functions), so
   everything downstream is language-agnostic.
4. Diff the two structural models by name.
5. Render: an SVG diagram (boxes laid out in rows, sized to fit their
   content, colored by change status, solid arrows for `extends` and
   dashed for `implements`), wrapped in an HTML page with a change-count
   summary and a full text breakdown.

## Using it in CI

See `.github/workflows/skyline.yml`. Today it generates the HTML report on
every PR update and uploads it as an artifact. The intended reviewer
surface is a **sticky PR comment** with the overlay and any policy
violations ([ADR 0002](docs/adr/0002-cli-ci-skill.md)). Artifacts alone
are not review.

## Development

Decisions and the implementation sequence: [docs/adr](docs/adr/README.md), [docs/plan.md](docs/plan.md).

```
git clone https://github.com/vivekchopra/skyline
cd skyline
pip install -e ".[dev]"
pytest
```

The codebase is small and split by concern:

| File | Responsibility |
| --- | --- |
| `skyline/model.py` | Shared, language-agnostic dataclasses (`ModuleModel`, `TypeEntity`, `Member`, `FunctionEntity`) |
| `skyline/python_extractor.py` | Python source to model (`ast`-based, including cyclomatic complexity) |
| `skyline/ts_extractor/extract.js` | TypeScript source to JSON (real TS compiler API, including complexity) |
| `skyline/ts_client.py` | Python wrapper: bootstraps the Node tooling, shells out, parses JSON to model |
| `skyline/languages.py` | Routes changed files to the right extractor by extension |
| `skyline/git_utils.py` | Read files from a repo at a given ref |
| `skyline/diff.py` | Diff two structural models (language-agnostic) |
| `skyline/crap.py` | CRAP scoring and coverage-map loading (see [Credit](#credit)) |
| `skyline/render_svg.py` | Structural diff to SVG diagram |
| `skyline/render_html.py` | SVG and summary to full HTML report |
| `skyline/cli.py` | `skyline diff` / `skyline demo` |

Adding a language means writing one more extractor that produces
`model.ModuleModel` objects and wiring it into `languages.py`. The diff
engine and both renderers need no changes.

## Roadmap

The implementation sequence is [docs/plan.md](docs/plan.md): honest unit
diffs, whole-tree snapshot, policy, PR overlay, data-model view, sticky
comment, project skill. Later, off that plan: auto-ingested coverage maps,
mutation scores, more languages, TypeScript `type` / `enum` / namespaces.

## License

MIT. See `LICENSE`.
