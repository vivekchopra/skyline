"""Markdown for the sticky pull-request comment.

The HTML report is the full picture. This comment is the lossy overlay a
reviewer sees without opening an artifact: violations, then the ADR 0001
review order, then Mermaid.
"""
from __future__ import annotations

from .links import finding_href
from .render_mermaid import coupling_mermaid, data_mermaid, diff_class_mermaid
from .review import HOW_TO_REVIEW

MARKER = "<!-- skyline-report -->"


def _finding_md(item, remote: str, base_sha: str, head_sha: str) -> str:
    text = getattr(item, "text", str(item))
    href = finding_href(remote, item, base_sha, head_sha)
    if not href:
        return text
    return f"[{text}]({href})"


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

    if review is not None and review.breaking:
        lines.append("### Breaking changes")
        lines.append("")
        for item in review.breaking:
            lines.append(f"- {_finding_md(item, remote, base_sha, head_sha)}")
        lines.append("")

    if review is not None and review.risks:
        lines.append("### Risk")
        lines.append("")
        for item in review.risks:
            lines.append(f"- {_finding_md(item, remote, base_sha, head_sha)}")
        lines.append("")

    if review is not None and review.untested:
        lines.append("### Untested new types")
        lines.append("")
        for item in review.untested:
            lines.append(f"- `{item}`")
        lines.append("")

    lines.append("### Overlay")
    lines.append("")
    lines.append("```mermaid")
    lines.append(diff_class_mermaid(diff))
    lines.append("```")
    lines.append("")
    lines.append("### Coupling")
    lines.append("")
    lines.append("```mermaid")
    lines.append(coupling_mermaid(diff))
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
