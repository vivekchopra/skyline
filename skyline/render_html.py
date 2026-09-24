"""Wrap the SVG diagram and a textual change summary into one self-contained
HTML report (no external assets, safe to open directly or attach to a PR)."""
from __future__ import annotations

import html

from .diff import ModelDiff
from .links import finding_href
from .render_svg import build_data_svg, build_diagram_svg
from .review import HOW_TO_REVIEW

STATUS_LABEL = {"added": "Added", "removed": "Removed", "modified": "Modified"}
STATUS_COLOR = {"added": "#2e7d32", "removed": "#c62828", "modified": "#e65100"}


def _esc(s: str) -> str:
    return html.escape(s)


def _crap_span(crap) -> str:
    if crap is None:
        return ""
    note = "" if crap.coverage_supplied else " (0% coverage assumed)"
    return f' <span style="color:{crap.color};font-weight:600">[{_esc(crap.label())}{note}]</span>'


def _chips(review, key: str) -> str:
    if review is None:
        return ""
    labels = review.chips.get(key) or []
    if not labels:
        return ""
    return " " + " ".join(f'<span class="chip">{_esc(label)}</span>' for label in labels)


def _function_rows(diff: ModelDiff, review=None) -> str:
    rows = []
    for fn in diff.functions:
        if fn.status == "unchanged":
            continue
        color = STATUS_COLOR[fn.status]
        detail = f" \u2014 {_esc(fn.reason)}" if fn.reason else ""
        rows.append(
            f'<li><code>{_esc(fn.path)}</code> :: <b style="color:{color}">'
            f'{STATUS_LABEL[fn.status]}</b> <code>{_esc(fn.name)}()</code>{detail}'
            f'{_crap_span(fn.crap)}{_chips(review, fn.qualname)}</li>'
        )
    return "\n".join(rows) if rows else "<li>No module-level function changes.</li>"


def _type_rows(diff: ModelDiff, review=None) -> str:
    rows = []
    for t in diff.types:
        if t.status == "unchanged":
            continue
        color = STATUS_COLOR[t.status]
        rows.append(
            f'<li><code>{_esc(t.path)}</code> :: <b style="color:{color}">{STATUS_LABEL[t.status]}</b> '
            f'<code>{_esc(t.kind)} {_esc(t.name)}</code>{_chips(review, t.qualname)}'
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
                    f'{detail}{_crap_span(m.crap)}{_chips(review, f"{t.qualname}.{m.name}")}</li>'
                )
            rows.append("</ul>")
        rows.append("</li>")
    return "\n".join(rows) if rows else "<li>No class/interface-level changes.</li>"


def _violation_html(diff: ModelDiff) -> str:
    items = [v for v in getattr(diff, "violations", []) if v.is_new]
    if not items:
        return ""
    rows = "\n".join(f"<li>{_esc(v.message)}</li>" for v in items)
    return f"<h2>Policy violations</h2>\n<ul>{rows}</ul>"


def _import_rows(diff: ModelDiff) -> str:
    rows = []
    for imp in diff.imports:
        if imp.status == "unchanged":
            continue
        color = STATUS_COLOR.get(imp.status, "#424242")
        label = STATUS_LABEL.get(imp.status, imp.status)
        rows.append(
            f'<li><b style="color:{color}">{label}</b> '
            f'<code>{_esc(imp.source)}</code> \u2192 <code>{_esc(imp.target)}</code></li>'
        )
    return "\n".join(rows) if rows else "<li>No resolved import changes.</li>"


def _finding_html(item, remote: str, base_sha: str, head_sha: str) -> str:
    text = getattr(item, "text", str(item))
    href = finding_href(remote, item, base_sha, head_sha)
    if not href:
        return _esc(text)
    return f'<a href="{_esc(href)}">{_esc(text)}</a>'


def build_html_report(diff: ModelDiff, base_ref: str, head_ref: str, repo_label: str = "",
                      policy=None, review=None, remote: str = "",
                      base_sha: str = "", head_sha: str = "") -> str:
    counts = diff.counts()
    layers = policy.layers if policy is not None else None
    layer_of = policy.layer_for if policy is not None else None
    svg = build_diagram_svg(diff, layers=layers, layer_of=layer_of)
    data_svg = build_data_svg(diff)
    violations = _violation_html(diff)
    data_section = (
        f'<h2>Data model</h2><div class="diagram">{data_svg}</div>' if data_svg else ""
    )
    caption = f'<p class="sub">{_esc(review.caption)}</p>' if review is not None else ""
    if review is not None and review.breaking:
        breaking_items = "".join(
            f"<li>{_finding_html(item, remote, base_sha, head_sha)}</li>" for item in review.breaking
        )
        breaking_strip = f"<h2>Breaking</h2><ul>{breaking_items}</ul>"
    else:
        breaking_strip = ""
    if review is not None and review.risks:
        risk_items = "".join(
            f"<li>{_finding_html(item, remote, base_sha, head_sha)}</li>" for item in review.risks
        )
        risk_strip = f'<h2>Risk</h2><ul class="risk">{risk_items}</ul>'
    else:
        risk_strip = ""
    coupling = f"<h2>Coupling</h2><ul>{_import_rows(diff)}</ul>"
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
  .chip {{ display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 8px; background: #eceff1; color: #37474f; font-size: 11px; }}
  .risk {{ margin-top: 0; }}
  .guide {{ max-width: 760px; margin: 12px 0 20px; padding-left: 18px; }}
  .guide li {{ font-size: 13px; margin: 4px 0; color: #333; }}
</style>
</head>
<body>
  <h1>Skyline</h1>
  <div class="sub">{_esc(repo_label)} &nbsp;\u00b7&nbsp; <code>{_esc(base_ref)}</code> \u2192 <code>{_esc(head_ref)}</code></div>
  <ul class="guide">
    {"".join(f"<li>{_esc(line)}</li>" for line in HOW_TO_REVIEW)}
  </ul>

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

  {caption}

  <div class="details">
    {violations}
    {breaking_strip}
    {risk_strip}
  </div>

  <div class="diagram">{svg}</div>

  <div class="details">
    {coupling}
  </div>

  {data_section}

  <div class="details">
    <h2>Classes &amp; interfaces</h2>
    <ul>{_type_rows(diff, review)}</ul>
    <h2>Module-level functions</h2>
    <ul>{_function_rows(diff, review)}</ul>
  </div>

  <p class="footer">
    This scoring approach, and the idea of overlaying it directly on a structural diagram, is
    inspired by Robert&nbsp;C.&nbsp;Martin's
    <a href="https://github.com/unclebob/uml-viewer" target="_blank" rel="noopener">uml-viewer</a>
    and <a href="https://github.com/unclebob/crap4clj" target="_blank" rel="noopener">crap4clj</a>.
    skyline is an independent, unaffiliated project.
  </p>
</body>
</html>
"""
