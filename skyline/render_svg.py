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
                 crap_badge: Optional[Tuple[str, str]] = None, note: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.note = note
        self.lines = lines
        self.status = "external" if external else status
        self.kind = kind
        self.external = external
        self.crap_badge = crap_badge
        shown_title = title if kind == "class" else f"\u00ab{kind}\u00bb {title}"
        text_lines = [note] if note else []
        if subtitle:
            text_lines.append(subtitle)
        text_lines.extend(t + (c or "") for t, _, c, _ in lines)
        widest = max((len(t) for t in text_lines), default=0)
        badge_w = (len(crap_badge[0]) * 6.3 + 16) if crap_badge else 0
        # One line per label. The box grows to the text so a signature is not cut off.
        header_w = len(shown_title) * 8.0 + badge_w + 2 * PADDING
        body_w = widest * CHAR_W + 2 * PADDING
        self.width = max(130, header_w, body_w)
        body_h = len(lines) * LINE_H
        self.height = HEADER_H + (LINE_H if note else 0) + (LINE_H if subtitle else 0) + body_h + PADDING
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
        if self.note:
            parts.append(
                f'<text x="{PADDING}" y="{y}" font-family="monospace" font-size="10" '
                f'fill="#666">{_esc(self.note)}</text>'
            )
            y += LINE_H
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


def _edge(sub_box: Box, target_box: Box, kind: str, width: float = 1.3) -> str:
    if target_box.y > sub_box.y:
        x1, y1 = sub_box.anchor_bottom()
        x2, y2 = target_box.anchor_top()
    else:
        x1, y1 = sub_box.anchor_top()
        x2, y2 = target_box.anchor_bottom()
    dash = "" if kind == "extends" else ' stroke-dasharray="4,3"'
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9e9e9e" '
        f'stroke-width="{width}"{dash} marker-end="url(#arrow)" />'
    )


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


def _layout_boxes(boxes: List[Box], layers=None) -> Tuple[int, int]:
    """Wrap rows by default. When a policy supplies layers, stack inner
    layers above outer ones instead of wrapping the overlay into one grid."""
    if not layers or not boxes:
        return _layout(boxes)
    return _layout_by_layer(boxes, layers)


def _layout_by_layer(boxes: List[Box], layers) -> Tuple[int, int]:
    """Place each layer on its own band, innermost first (top). Boxes with
    no layer sit in a final band. ``layers`` is an ordered list of layer names."""
    bands: Dict[str, List[Box]] = {name: [] for name in layers}
    rest: List[Box] = []
    for box in boxes:
        layer = getattr(box, "layer", None)
        if layer in bands:
            bands[layer].append(box)
        else:
            rest.append(box)
    y = 0.0
    max_x = 0.0
    for name in list(layers) + [None]:
        group = bands.get(name, rest) if name is not None else rest
        if not group:
            continue
        x = 0.0
        row_h = 0.0
        for box in group:
            if x > 0 and x + box.width > MAX_ROW_WIDTH:
                x = 0.0
                y += row_h + BOX_GAP_Y
                row_h = 0.0
            box.x, box.y = x, y
            x += box.width + BOX_GAP_X
            row_h = max(row_h, box.height)
            max_x = max(max_x, x)
        y += row_h + BOX_GAP_Y + 28
    return int(max_x), int(max(y - BOX_GAP_Y, 0))


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


_CHANGED = ("added", "removed", "modified")


def _resolve_relation_target(source, target_name: str, types) -> str:
    """Prefer a same-file changed type, else any changed type, else a type
    already in the diff (neighborhood), else a synthetic external box."""
    others = [t for t in types if t.name == target_name and t.qualname != source.qualname]
    same_file = [t for t in others if t.path == source.path]
    for pool in (
        [t for t in same_file if t.status in _CHANGED],
        [t for t in others if t.status in _CHANGED],
        same_file,
        others,
    ):
        if pool:
            return pool[0].qualname
    return f"external::{target_name}"


def _function_line(fn) -> Tuple[str, str, Optional[str], Optional[str]]:
    sig = fn.after or fn.before
    params = ", ".join(sig.params) if sig else ""
    sym = {"added": "+", "removed": "\u2212", "modified": "~"}.get(fn.status, " ")
    color = {"added": "#2e7d32", "removed": "#c62828", "modified": "#e65100"}.get(fn.status, "#424242")
    crap_label = f"  {fn.crap.label()}" if fn.crap is not None else None
    crap_color = fn.crap.color if fn.crap is not None else None
    return f"{sym} {fn.name}({params})", color, crap_label, crap_color


def build_diagram_svg(diff: ModelDiff, layers=None, layer_of=None) -> str:
    by_qual = {t.qualname: t for t in diff.types}
    primary = [t for t in diff.types if t.status in _CHANGED]
    resolved_targets = {}
    for t in primary:
        resolved_targets[t.qualname] = [
            (_resolve_relation_target(t, target, diff.types), kind)
            for target, kind in t.relations
        ]

    drawn_types = list(primary)
    seen = {t.qualname for t in drawn_types}
    for targets in resolved_targets.values():
        for key, _kind in targets:
            if key in seen or key not in by_qual:
                continue
            drawn_types.append(by_qual[key])
            seen.add(key)
    for imp in diff.imports:
        if imp.status not in ("added", "removed"):
            continue
        for type_change in diff.types:
            if type_change.path not in (imp.source, imp.target) or type_change.qualname in seen:
                continue
            drawn_types.append(type_change)
            seen.add(type_change.qualname)

    name_counts: Dict[str, int] = {}
    for t in drawn_types:
        name_counts[t.name] = name_counts.get(t.name, 0) + 1
    changed_fns = [fn for fn in diff.functions if fn.status in _CHANGED]
    fn_counts: Dict[str, int] = {}
    for fn in changed_fns:
        fn_counts[fn.name] = fn_counts.get(fn.name, 0) + 1

    boxes: Dict[str, Box] = {}
    for t in drawn_types:
        neighborhood = t.status not in _CHANGED
        lines = [] if neighborhood else [_member_line(m) for m in t.members if m.status != "unchanged"]
        note = t.path if name_counts[t.name] > 1 else ""
        boxes[t.qualname] = Box(
            title=t.name, subtitle="" if neighborhood else _relation_subtitle(t), lines=lines,
            status="external" if neighborhood else t.status, kind=t.kind,
            external=neighborhood, crap_badge=None if neighborhood else _worst_crap_badge(t),
            note=note,
        )
    for targets in resolved_targets.values():
        for key, _kind in targets:
            if key in boxes:
                continue
            boxes[key] = Box(title=key.split("::", 1)[-1], subtitle="", lines=[],
                              status="external", external=True)

    for fn in changed_fns:
        key = fn.qualname if fn.qualname not in boxes else f"{fn.qualname}#function"
        note = fn.path if fn_counts[fn.name] > 1 else ""
        badge = (fn.crap.label(), fn.crap.color) if fn.crap is not None else None
        boxes[key] = Box(
            title=fn.name, subtitle="", lines=[_function_line(fn)],
            status=fn.status, kind="function", crap_badge=badge, note=note,
        )
        boxes[key].origin = fn.path

    for box_key, box in list(boxes.items()):
        if not hasattr(box, "origin"):
            origin = box_key.split("#", 1)[0]
            if "::" in origin and not origin.startswith("external::") and not origin.startswith("file::"):
                box.origin = origin.split("::", 1)[0]
            else:
                box.origin = ""

    present_edges = {
        (imp.source, imp.target) for imp in diff.imports if imp.status in ("added", "unchanged")
    }
    for imp in diff.imports:
        if imp.status not in ("added", "removed"):
            continue
        for path in (imp.source, imp.target):
            if any(getattr(box, "origin", "") == path for box in boxes.values()):
                continue
            file_key = f"file::{path}"
            boxes[file_key] = Box(title=path, subtitle="", lines=[], status="external", external=True)
            boxes[file_key].origin = path

    if layer_of is not None:
        for box in boxes.values():
            origin = getattr(box, "origin", "")
            box.layer = layer_of(origin) if origin else None

    box_list = list(boxes.values())
    width, height = _layout_boxes(box_list, layers)

    edges_svg = []
    for t in primary:
        sub_box = boxes.get(t.qualname)
        if sub_box is None:
            continue
        for key, kind in resolved_targets.get(t.qualname, []):
            target_box = boxes.get(key)
            if target_box is None or target_box is sub_box:
                continue
            edges_svg.append(_edge(sub_box, target_box, kind))

    def _box_for(path: str):
        for box in boxes.values():
            if getattr(box, "origin", "") == path:
                return box
        return None

    for imp in diff.imports:
        if imp.status not in ("added", "removed"):
            continue
        src_box = _box_for(imp.source)
        dst_box = _box_for(imp.target)
        if src_box is None or dst_box is None or src_box is dst_box:
            continue
        mutual = (imp.target, imp.source) in present_edges
        kind = "imports" if imp.status == "added" else "removed-import"
        edges_svg.append(_edge(src_box, dst_box, kind, width=2.6 if mutual else 1.3))

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


def build_data_svg(diff: ModelDiff) -> str:
    """Second diagram: tables and columns, not class members."""
    tables = [t for t in diff.tables if t.status in _CHANGED]
    if not tables:
        return ""
    boxes: Dict[str, Box] = {}
    for table in tables:
        lines = []
        for col in table.columns:
            if col.status == "unchanged":
                continue
            sym = {"added": "+", "removed": "\u2212", "modified": "~"}.get(col.status, " ")
            color = {"added": "#2e7d32", "removed": "#c62828", "modified": "#e65100"}.get(col.status, "#424242")
            shown = col.after or col.before or ""
            suffix = f": {shown}" if shown else ""
            lines.append((f"{sym} {col.name}{suffix}", color, None, None))
        boxes[table.qualname] = Box(
            title=table.name, subtitle="", lines=lines, status=table.status, kind="table", note=table.path,
        )
    box_list = list(boxes.values())
    width, height = _layout(box_list)
    edges = []
    by_name = {}
    for table in tables:
        by_name.setdefault(table.name, table.qualname)
    for table in tables:
        src = boxes.get(table.qualname)
        if src is None:
            continue
        for relation in table.relations:
            target_name = relation.split(".")[-1]
            dst = boxes.get(by_name.get(target_name, ""))
            if dst is not None and dst is not src:
                edges.append(_edge(src, dst, "extends"))
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#9e9e9e" /></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="white" />',
    ]
    svg.extend(edges)
    for box in box_list:
        svg.append(box.render())
    svg.append("</svg>")
    return "".join(svg)
