# ADR 0003: JSON export and prompt bundling

## Status

Accepted

## Date

2026-09-24

## Context

ADR 0002 makes the project skill a trigger: it runs the CLI and reads the report. It does not analyze the diff itself. The next slice of that skill is handing the structural model to an agent, with a ranking prompt the team can edit.

The structural model is already computed for the HTML report: types, functions, breaking changes, CRAP, coupling, the data model, violations. An agent needs that data as JSON, and a prompt that says how to rank it. Those are different artifacts. The JSON is a render of the diff. The prompt is a judgment call (what to read first, what counts as an architecture flag). Teams will tune the judgment per repo, the way they tune `skyline.policy.toml`. They will not want a skyline release to change the ranking text.

JSON generation reuses the diff already in memory. It does not depend on writing an HTML file, and it does not require a separate analysis pass.

## Decision

**Two independent flags. Not one feature.**

```text
skyline diff
    ├── --format html          (default; unchanged)
    ├── --format json          structural data only
    └── --emit-prompt out.md   template + that JSON, one file
            └── --prompt-template path.md   (default: skyline/prompts/review.md)
```

1. **`--format json`** is a renderer beside `render_html.py` and `render_svg.py`. Input is the existing diff: types, functions, breaking changes (including dependents), CRAP, coupling, data model, violations, stats. No new detection. The risk list in JSON is the full scored set. The HTML report still shows its short top-five summary.

2. **`--emit-prompt`** writes one markdown file: a prompt template with the JSON substituted at a single marker, `{{SKYLINE_DATA}}`. It always builds that JSON internally, whether or not `--format json` was passed. `--out` and `--format` stay optional. Passing them in the same run still writes the report.

3. **The template is a file, not a Python string.** The default ships at `skyline/prompts/review.md`. `--prompt-template` points at a repo-local copy, the same idea as `skyline.policy.toml`: the team owns the ranking text. A custom template that lacks `{{SKYLINE_DATA}}` fails the run. The data is not silently dropped.

4. **This is the first slice of the project skill** (plan step 10), not a new product. The skill keeps invoking the CLI. The CLI gains a way to hand the model to an agent.

### Do not

- Add detection in this pass. Policy violations, CRAP, coupling, and untested types stay as they are.
- Change `.github/workflows/skyline.yml` to post the prompt. Wiring the file into CI is a follow-up.
- Add a templating library. One string replacement is enough.
- Let `--format` be inferred from the `--out` extension. The flag chooses the renderer.

## Consequences

### Positive

- An agent can consume the same model the HTML report shows, without scraping HTML.
- A repo can edit the ranking prompt without a skyline release.
- `--emit-prompt` works on its own. JSON is cheap because the diff is already built.

### Negative / trade-offs

- Two output files when both flags are set. That is intentional: the report is for a human, the prompt file is for an agent.
- The default prompt will be wrong for some teams. That is why it is a file they can copy.

### Follow-up

- CI does not emit or post the prompt yet. A later change can add `--emit-prompt` to the workflow once a repo wants that file on the PR. Not this ADR.
- The skill text can tell an agent to run `--emit-prompt` and then follow the file. That edit is documentation, after the flags exist.

## Alternatives considered

- **One flag that writes JSON and a prompt together.** Forces every JSON user through the prompt, and every prompt user through a format flag. Rejected.
- **Hardcode the prompt in Python.** A ranking change would need a release. Rejected. Same reason policy is TOML.
- **MCP as the way an agent gets the model.** ADR 0002 already deferred MCP. A JSON file is enough for this slice.
