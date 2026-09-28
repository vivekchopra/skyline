"""Markdown for the sticky pull-request comment.

The HTML report is the full picture. This comment is the lossy overlay a
reviewer sees without opening an artifact: violations, then the ADR 0001
review order, then Mermaid.
"""
from __future__ import annotations

from .links import finding_href
from .render_mermaid import data_mermaid, diff_class_mermaid
from .review import HOW_TO_REVIEW, dropped_line, generated_line

MARKER = "<!-- skyline-report -->"


def _finding_md(item, remote: str, base_sha: str, head_sha: str) -> str:
    text = getattr(item, "text", str(item))
    href = finding_href(remote, item, base_sha, head_sha)
    if not href:
        return text
    return f"[{text}]({href})"


def _section(lines, title, items, remote, base_sha, head_sha) -> None:
    if not items:
        return
    lines.append(f"### {title}")
    lines.append("")
    for item in items:
        lines.append(f"- {_finding_md(item, remote, base_sha, head_sha)}")
    lines.append("")


def render_comment(diff, review, base_ref: str, head_ref: str,
                   remote: str = "", base_sha: str = "", head_sha: str = "") -> str:
    lines = [
        MARKER,
        "",
        "## Skyline",
        "",
        f"`{base_ref}` \u2192 `{head_ref}`",
        "",
        "How to review:",
        "",
    ]
    lines.extend(f"- {line}" for line in HOW_TO_REVIEW)
    lines.append("")
    if review is not None and review.caption:
        lines.append(review.caption)
        lines.append("")
    if review is not None and generated_line(review):
        lines.append(generated_line(review))
        lines.append("")

    violations = [v for v in getattr(diff, "violations", []) if getattr(v, "is_new", False)]
    if violations:
        lines.append("### Policy violations")
        lines.append("")
        for violation in violations:
            lines.append(f"- {violation.message}")
        lines.append("")

    counts = diff.counts()
    lines.append(
        "types "
        f"+{counts['types_added']} -{counts['types_removed']} ~{counts['types_modified']}"
        " · functions "
        f"+{counts['functions_added']} -{counts['functions_removed']} ~{counts['functions_modified']}"
    )
    lines.append("")

    if review is not None:
        _section(lines, "Schema", review.schema, remote, base_sha, head_sha)
        _section(lines, "Untested", review.untested, remote, base_sha, head_sha)
        _section(lines, "Changed behavior", review.changed, remote, base_sha, head_sha)
        _section(lines, "Hotspots touched", review.hotspots, remote, base_sha, head_sha)
        _section(lines, "Breaking", review.breaking, remote, base_sha, head_sha)
        note = dropped_line(review)
        if note:
            lines.append(note)
            lines.append("")
        lines.append("### Coupling")
        lines.append("")
        for item in review.coupling:
            lines.append(item if item == "none" else f"- {item}")
        lines.append("")

    lines.append("### Overlay")
    lines.append("")
    lines.append("```mermaid")
    lines.append(diff_class_mermaid(diff))
    lines.append("```")
    lines.append("")
    data = data_mermaid(diff)
    if data:
        lines.append("### Data model")
        lines.append("")
        lines.append("```mermaid")
        lines.append(data)
        lines.append("```")
        lines.append("")

    lines.append(
        "Mermaid is a lossy overlay. The HTML artifact is the diagram with CRAP and neighborhood."
    )
    lines.append("")
    return "\n".join(lines)
