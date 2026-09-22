"""Render a ModelDiff as a self-contained SVG UML-style class diagram.

Only changed types are drawn as full boxes (added / removed / modified).
Unchanged types referenced by a changed type's relations (e.g. an
unmodified base class) are drawn as small dashed "external" boxes so the
reviewer still sees where the change plugs into the existing hierarchy.

Two relation kinds get distinct UML-standard line styles:
  extends    -> solid line, hollow triangle head   (inheritance)
  implements -> dashed line, hollow triangle head   (interface realization)
"""
from __future__ import annotations

import html
from typing import Dict, List, Optional, Tuple

from .diff import ModelDiff

COLORS = {
    "added": ("#e6f4ea", "#2e7d32"),
    "removed": ("#fdecea", "#c62828"),
    "modified": ("#fff8e1", "#e65100"),
    "external": ("#f0f0f0", "#9e9e9e"),
}

CHAR_W = 7.2
LINE_H = 16
PADDING = 10
HEADER_H = 24
BOX_GAP_X = 30
BOX_GAP_Y = 40
MAX_ROW_WIDTH = 1180


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _member_line(m) -> Tuple[str, str, Optional[str], Optional[str]]:
    sym = {"added": "+", "removed": "\u2212", "modified": "~"}.get(m.status, " ")
    color = {"added": "#2e7d32", "removed": "#c62828", "modified": "#e65100"}.get(m.status, "#424242")
    sig = m.after or m.before
    if sig is None:
        return f"{sym} {m.name}", color, None, None
    if sig.kind == "property":
        rt = f": {sig.return_type}" if sig.return_type else ""
        text = f"{sym} {sig.name}{rt}"
    else:
        text = f"{sym} {sig.name}({', '.join(sig.params)})"
    crap_label = f"  {m.crap.label()}" if m.crap is not None else None
    crap_color = m.crap.color if m.crap is not None else None
    return text, color, crap_label, crap_color


class Box:
    def __init__(self, title: str, subtitle: str, lines: List[Tuple[str, str, Optional[str], Optional[str]]],
                 status: str, kind: str = "class", external: bool = False,
                 crap_badge: Optional[Tuple[str, str]] = None):
        self.title = title
        self.subtitle = subtitle
        self.lines = lines
        self.status = "external" if external else status
        self.kind = kind
        self.external = external
        self.crap_badge = crap_badge
        text_lines = [title] + ([subtitle] if subtitle else []) + [t + (c or "") for t, _, c, _ in lines]
        widest = max((len(t) for t in text_lines), default=10)
        badge_w = (len(crap_badge[0]) * CHAR_W + 16) if crap_badge else 0
        self.width = max(130, min(460, max(widest * CHAR_W + 2 * PADDING, badge_w + widest * CHAR_W * 0.4)))
        body_h = len(lines) * LINE_H
        self.height = HEADER_H + (LINE_H if subtitle else 0) + body_h + PADDING
        self.x = 0.0
        self.y = 0.0

    def render(self) -> str:
        fill, border = COLORS[self.status]
        dash = ' stroke-dasharray="5,3"' if self.external else ""
        parts = [f'<g transform="translate({self.x},{self.y})">']
        parts.append(
            f'<rect width="{self.width}" height="{self.height}" rx="6" '
            f'fill="{fill}" stroke="{border}" stroke-width="1.5"{dash} />'
        )
        parts.append(f'<line x1="0" y1="{HEADER_H}" x2="{self.width}" y2="{HEADER_H}" stroke="{border}" />')
        label = self.title if self.kind == "class" else f"\u00ab{self.kind}\u00bb {self.title}"
        title_x = self.width / 2 if not self.crap_badge else max(self.width / 2 - 24, PADDING + 30)
        parts.append(
            f'<text x="{title_x}" y="{HEADER_H / 2 + 5}" text-anchor="middle" '
            f'font-family="monospace" font-weight="bold" font-size="12.5" fill="{border}">{_esc(label)}</text>'
        )
        if self.crap_badge:
            badge_label, badge_color = self.crap_badge
            bw = len(badge_label) * 6.3 + 10
            bx = self.width - bw - 6
            parts.append(
                f'<rect x="{bx}" y="4" width="{bw}" height="16" rx="4" fill="{badge_color}" />'
                f'<text x="{bx + bw / 2}" y="15.5" text-anchor="middle" '
                f'font-family="monospace" font-size="10" font-weight="bold" fill="white">{_esc(badge_label)}</text>'
            )
        y = HEADER_H + LINE_H - 4
        if self.subtitle:
            parts.append(
                f'<text x="{PADDING}" y="{y}" font-family="monospace" font-size="11" '
                f'fill="{border}" font-style="italic">{_esc(self.subtitle)}</text>'
            )
            y += LINE_H
        for text, color, crap_label, crap_color in self.lines:
            crap_tspan = (
                f'<tspan fill="{crap_color}" font-weight="bold">{_esc(crap_label)}</tspan>'
                if crap_label else ""
            )
            parts.append(
                f'<text x="{PADDING}" y="{y}" font-family="monospace" font-size="11">'
                f'<tspan fill="{color}">{_esc(text)}</tspan>{crap_tspan}</text>'
            )
            y += LINE_H
        parts.append("</g>")
        return "".join(parts)

    def anchor_top(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y)

    def anchor_bottom(self) -> Tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height)


def _layout(boxes: List[Box]) -> Tuple[int, int]:
    x, y, row_h, max_x = 0.0, 0.0, 0.0, 0.0
    for box in boxes:
        if x > 0 and x + box.width > MAX_ROW_WIDTH:
            x = 0.0
            y += row_h + BOX_GAP_Y
            row_h = 0.0
        box.x, box.y = x, y
        x += box.width + BOX_GAP_X
        row_h = max(row_h, box.height)
        max_x = max(max_x, x)
    return int(max_x), int(y + row_h)


def _relation_subtitle(t) -> str:
    if t.added_relations or t.removed_relations:
        parts = []
        if t.added_relations:
            parts.append("+" + ", ".join(n for n, k in t.added_relations))
        if t.removed_relations:
            parts.append("\u2212" + ", ".join(n for n, k in t.removed_relations))
        return "\u2192 " + " ".join(parts)
    if t.relations:
        return "\u2192 " + ", ".join(n for n, k in t.relations)
    return ""


def _worst_crap_badge(t) -> Optional[Tuple[str, str]]:
    scored = [m.crap for m in t.members if m.crap is not None]
    if not scored:
        return None
    worst = max(scored, key=lambda c: c.value)
    return worst.label(), worst.color


def build_diagram_svg(diff: ModelDiff) -> str:
    primary = [t for t in diff.types if t.status in ("added", "removed", "modified")]
    primary_names = {t.name for t in primary}

    boxes: Dict[str, Box] = {}
    external_names = set()

    for t in primary:
        lines = [_member_line(m) for m in t.members if m.status != "unchanged"]
        boxes[t.name] = Box(title=t.name, subtitle=_relation_subtitle(t), lines=lines,
                             status=t.status, kind=t.kind, crap_badge=_worst_crap_badge(t))
        for target, _kind in t.relations:
            if target not in primary_names:
                external_names.add(target)

    for name in sorted(external_names):
        boxes[name] = Box(title=name, subtitle="", lines=[], status="external", external=True)

    box_list = list(boxes.values())
    width, height = _layout(box_list)

    edges_svg = []
    for t in primary:
        sub_box = boxes.get(t.name)
        if sub_box is None:
            continue
        for target, kind in t.relations:
            target_box = boxes.get(target)
            if target_box is None or target == t.name:
                continue
            if target_box.y > sub_box.y:
                x1, y1 = sub_box.anchor_bottom()
                x2, y2 = target_box.anchor_top()
            else:
                x1, y1 = sub_box.anchor_top()
                x2, y2 = target_box.anchor_bottom()
            dash = "" if kind == "extends" else ' stroke-dasharray="4,3"'
            edges_svg.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9e9e9e" '
                f'stroke-width="1.3"{dash} marker-end="url(#arrow)" />'
            )

    if not box_list:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="440" height="50">'
            '<text x="10" y="28" font-family="sans-serif" font-size="13">'
            'No class/interface-level structural changes detected.</text></svg>'
        )

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#9e9e9e" /></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="white" />',
    ]
    svg.extend(edges_svg)
    for box in box_list:
        svg.append(box.render())
    svg.append("</svg>")
    return "".join(svg)
