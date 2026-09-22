"""Wrap the SVG diagram and a textual change summary into one self-contained
HTML report (no external assets, safe to open directly or attach to a PR)."""
from __future__ import annotations

import html

from .diff import ModelDiff
from .render_svg import build_diagram_svg

STATUS_LABEL = {"added": "Added", "removed": "Removed", "modified": "Modified"}
STATUS_COLOR = {"added": "#2e7d32", "removed": "#c62828", "modified": "#e65100"}


def _esc(s: str) -> str:
    return html.escape(s)


def _crap_span(crap) -> str:
    if crap is None:
        return ""
    note = "" if crap.coverage_supplied else " (0% coverage assumed)"
    return f' <span style="color:{crap.color};font-weight:600">[{_esc(crap.label())}{note}]</span>'


def _function_rows(diff: ModelDiff) -> str:
    rows = []
    for fn in diff.functions:
        if fn.status == "unchanged":
            continue
        color = STATUS_COLOR[fn.status]
        detail = f" \u2014 {_esc(fn.reason)}" if fn.reason else ""
        rows.append(
            f'<li><code>{_esc(fn.path)}</code> :: <b style="color:{color}">'
            f'{STATUS_LABEL[fn.status]}</b> <code>{_esc(fn.name)}()</code>{detail}{_crap_span(fn.crap)}</li>'
        )
    return "\n".join(rows) if rows else "<li>No module-level function changes.</li>"


def _type_rows(diff: ModelDiff) -> str:
    rows = []
    for t in diff.types:
        if t.status == "unchanged":
            continue
        color = STATUS_COLOR[t.status]
        rows.append(
            f'<li><code>{_esc(t.path)}</code> :: <b style="color:{color}">{STATUS_LABEL[t.status]}</b> '
            f'<code>{_esc(t.kind)} {_esc(t.name)}</code>'
        )
        member_items = [m for m in t.members if m.status != "unchanged"]
        if member_items or t.added_relations or t.removed_relations:
            rows.append("<ul>")
            for target, kind in t.added_relations:
                rows.append(f'<li style="color:#2e7d32">+ {kind} <code>{_esc(target)}</code></li>')
            for target, kind in t.removed_relations:
                rows.append(f'<li style="color:#c62828">\u2212 no longer {kind} <code>{_esc(target)}</code></li>')
            for m in member_items:
                mcolor = STATUS_COLOR[m.status]
                detail = f" \u2014 {_esc(m.reason)}" if m.reason else ""
                rows.append(
                    f'<li style="color:{mcolor}">{STATUS_LABEL[m.status]} <code>{_esc(m.name)}</code>'
                    f'{detail}{_crap_span(m.crap)}</li>'
                )
            rows.append("</ul>")
        rows.append("</li>")
    return "\n".join(rows) if rows else "<li>No class/interface-level changes.</li>"


def build_html_report(diff: ModelDiff, base_ref: str, head_ref: str, repo_label: str = "") -> str:
    counts = diff.counts()
    svg = build_diagram_svg(diff)
    title = (
        f"skyline diff \u2014 {repo_label} {base_ref}...{head_ref}"
        if repo_label else f"skyline diff \u2014 {base_ref}...{head_ref}"
    )

    summary_items = "".join(
        f'<div class="stat"><span class="n">{v}</span><span class="l">{k.replace("_", " ")}</span></div>'
        for k, v in counts.items() if v
    ) or '<div class="stat"><span class="n">0</span><span class="l">structural changes</span></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{_esc(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 24px; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 18px; margin-bottom: 4px; }}
  .sub {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .legend span {{ display:inline-block; margin-right: 16px; font-size: 12px; }}
  .swatch {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:middle; }}
  .stats {{ display: flex; gap: 18px; margin: 16px 0 24px; flex-wrap: wrap; }}
  .stat {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px 16px; min-width: 90px; text-align: center; }}
  .stat .n {{ display:block; font-size: 20px; font-weight: 700; }}
  .stat .l {{ display:block; font-size: 11px; color: #777; text-transform: uppercase; letter-spacing: .03em; }}
  .diagram {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; overflow: auto; margin-bottom: 28px; }}
  .details {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px 24px; }}
  .details h2 {{ font-size: 15px; }}
  code {{ background: #f1f1f1; padding: 1px 4px; border-radius: 3px; font-size: 12.5px; }}
  ul {{ margin: 4px 0; }}
  li {{ font-size: 13px; margin: 2px 0; }}
  .footer {{ color: #999; font-size: 11.5px; margin-top: 20px; line-height: 1.6; max-width: 760px; }}
  .footer a {{ color: #888; }}
</style>
</head>
<body>
  <h1>Skyline</h1>
  <div class="sub">{_esc(repo_label)} &nbsp;\u00b7&nbsp; <code>{_esc(base_ref)}</code> \u2192 <code>{_esc(head_ref)}</code></div>

  <div class="legend">
    <span><i class="swatch" style="background:#2e7d32"></i>added</span>
    <span><i class="swatch" style="background:#c62828"></i>removed</span>
    <span><i class="swatch" style="background:#e65100"></i>modified</span>
    <span><i class="swatch" style="background:#9e9e9e"></i>external / unchanged reference</span>
  </div>
  <div class="legend">
    <span style="color:#888">CRAP score:</span>
    <span><i class="swatch" style="background:#2e7d32"></i>low (\u22645)</span>
    <span><i class="swatch" style="background:#f9a825"></i>moderate (\u226410)</span>
    <span><i class="swatch" style="background:#e65100"></i>high (\u226430)</span>
    <span><i class="swatch" style="background:#c62828"></i>severe (&gt;30)</span>
  </div>

  <div class="stats">{summary_items}</div>

  <div class="diagram">{svg}</div>

  <div class="details">
    <h2>Classes &amp; interfaces</h2>
    <ul>{_type_rows(diff)}</ul>
    <h2>Module-level functions</h2>
    <ul>{_function_rows(diff)}</ul>
  </div>

  <p class="footer">
    CRAP (Change Risk Anti-Patterns) score = complexity\u00b2 \u00d7 (1 \u2212 coverage)\u00b3 + complexity.
    Shown on added/modified methods and functions only. Coverage not supplied for this run is
    treated as 0% (worst case), not "unknown."
    This scoring approach, and the idea of overlaying it directly on a structural diagram, is
    inspired by Robert&nbsp;C.&nbsp;Martin's
    <a href="https://github.com/unclebob/uml-viewer" target="_blank" rel="noopener">uml-viewer</a>
    and <a href="https://github.com/unclebob/crap4clj" target="_blank" rel="noopener">crap4clj</a>.
    skyline is an independent, unaffiliated project.
  </p>
</body>
</html>
"""
