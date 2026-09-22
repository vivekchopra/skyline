"""As-intended architecture: layers, allowed edges, and violations.

No policy file means the overlay still runs and nothing is illegal.
Pictures without a rule are not a throttle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def _loads(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    return tomllib.loads(text)


@dataclass
class Violation:
    kind: str  # "illegal_edge" | "wrong_package" | "layer_cycle" | "wrong_owner"
    message: str
    source: str = ""
    target: str = ""
    is_new: bool = True


@dataclass
class Policy:
    layers: List[str]
    ranks: Dict[str, int]
    prefixes: Dict[str, List[str]]
    allow: Set[Tuple[str, str]] = field(default_factory=set)
    same_rank: bool = True
    omit: List[str] = field(default_factory=list)
    proposals: Dict[str, str] = field(default_factory=dict)
    data_owners: Dict[str, List[str]] = field(default_factory=dict)

    def layer_for(self, path: str) -> Optional[str]:
        if any(path.startswith(prefix) for prefix in self.omit):
            return None
        best_name = None
        best_len = -1
        for name, prefixes in self.prefixes.items():
            for prefix in prefixes:
                if path.startswith(prefix) and len(prefix) > best_len:
                    best_name = name
                    best_len = len(prefix)
        return best_name

    def allows(self, src_layer: Optional[str], dst_layer: Optional[str]) -> bool:
        """Unranked files are never a violation. Same rank is allowed unless
        the policy says otherwise. Otherwise an edge may point at a more
        inner layer (downward), plus any explicit ``allow`` exception."""
        if src_layer is None or dst_layer is None:
            return True
        if (src_layer, dst_layer) in self.allow:
            return True
        if self.ranks[src_layer] == self.ranks[dst_layer]:
            return self.same_rank
        return self.ranks[dst_layer] < self.ranks[src_layer]


def _default_prefixes(name: str) -> List[str]:
    if name.endswith("/"):
        return [name]
    return [f"{name}/", f"{name}.py", f"{name}.ts", f"{name}.tsx"]


def parse_policy(text: str) -> Policy:
    data = _loads(text)
    layers: List[str] = []
    ranks: Dict[str, int] = {}
    prefixes: Dict[str, List[str]] = {}

    layer_table = data.get("layer") or {}
    if isinstance(layer_table, dict) and layer_table:
        items = []
        for name, spec in layer_table.items():
            spec = spec or {}
            rank = int(spec.get("rank", 0))
            prefs = list(spec.get("prefixes") or _default_prefixes(str(name)))
            items.append((rank, str(name), prefs))
        for rank, name, prefs in sorted(items, key=lambda item: (item[0], item[1])):
            layers.append(name)
            ranks[name] = rank
            prefixes[name] = prefs
    elif isinstance(data.get("layers"), list):
        for index, name in enumerate(data["layers"]):
            name = str(name)
            layers.append(name)
            ranks[name] = index
            prefixes[name] = _default_prefixes(name)

    allow: Set[Tuple[str, str]] = set()
    for item in data.get("allow") or []:
        if isinstance(item, str) and "->" in item:
            src, dst = [part.strip() for part in item.split("->", 1)]
            allow.add((src, dst))
        elif isinstance(item, dict) and "from" in item and "to" in item:
            allow.add((str(item["from"]), str(item["to"])))

    owners: Dict[str, List[str]] = {}
    data_table = data.get("data") or {}
    if isinstance(data_table, dict):
        for prefix, tables in (data_table.get("owners") or {}).items():
            owners[str(prefix)] = [str(name) for name in tables]

    proposals = data.get("proposals") or {}
    return Policy(
        layers=layers,
        ranks=ranks,
        prefixes=prefixes,
        allow=allow,
        same_rank=bool(data.get("same_rank", True)),
        omit=[str(item) for item in (data.get("omit") or [])],
        proposals={str(k): str(v) for k, v in proposals.items()} if isinstance(proposals, dict) else {},
        data_owners=owners,
    )


def load_policy(path: Optional[str]) -> Optional[Policy]:
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    return parse_policy(file.read_text(encoding="utf-8"))


def find_violations(diff, policy: Optional[Policy]) -> List[Violation]:
    if policy is None:
        return []
    violations: List[Violation] = []
    for imp in diff.imports:
        if imp.status not in ("added", "unchanged"):
            continue
        src_layer = policy.layer_for(imp.source)
        dst_layer = policy.layer_for(imp.target)
        if policy.allows(src_layer, dst_layer):
            continue
        violations.append(Violation(
            kind="illegal_edge",
            message=(
                f"Illegal edge {imp.source} \u2192 {imp.target} "
                f"({src_layer} \u2192 {dst_layer})"
            ),
            source=imp.source,
            target=imp.target,
            is_new=imp.status == "added",
        ))

    head_edges = [(imp.source, imp.target) for imp in diff.imports if imp.status in ("added", "unchanged")]
    for type_change in diff.types:
        if type_change.status != "added":
            continue
        src_layer = policy.layer_for(type_change.path)
        if src_layer is None:
            continue
        for source, target in head_edges:
            if source != type_change.path:
                continue
            dst_layer = policy.layer_for(target)
            if policy.allows(src_layer, dst_layer):
                continue
            violations.append(Violation(
                kind="wrong_package",
                message=(
                    f"Type {type_change.name} in {type_change.path} is in the wrong package: "
                    f"imports {target} ({src_layer} \u2192 {dst_layer})"
                ),
                source=type_change.path,
                target=target,
                is_new=True,
            ))

    violations.extend(_new_layer_cycles(diff, policy))
    violations.extend(_wrong_owners(diff, policy))
    return violations


def _wrong_owners(diff, policy: Policy) -> List[Violation]:
    if not policy.data_owners:
        return []
    violations = []
    for table in getattr(diff, "tables", []):
        if table.status not in ("added", "modified"):
            continue
        owner_prefix = None
        owner_names: List[str] = []
        best = -1
        for prefix, names in policy.data_owners.items():
            if table.path.startswith(prefix) and len(prefix) > best:
                owner_prefix = prefix
                owner_names = names
                best = len(prefix)
        if owner_names and any(table.name == name or table.name.startswith(name) for name in owner_names):
            continue
        claimed = [
            prefix for prefix, names in policy.data_owners.items()
            if prefix != owner_prefix and any(table.name == name or table.name.startswith(name) for name in names)
        ]
        if not claimed:
            continue
        violations.append(Violation(
            kind="wrong_owner",
            message=(
                f"Table {table.name} in {table.path} is owned by {claimed[0]}, "
                f"not by {owner_prefix or 'this package'}"
            ),
            source=table.path,
            target=table.name,
            is_new=table.status == "added",
        ))
    return violations


def _graph(diff, statuses) -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = {}
    for imp in diff.imports:
        if imp.status in statuses:
            graph.setdefault(imp.source, set()).add(imp.target)
    return graph


def _cycles(graph: Dict[str, Set[str]]) -> List[Tuple[str, ...]]:
    found: List[Tuple[str, ...]] = []
    seen: Set[str] = set()
    for start in graph:
        stack = [(start, [start], {start})]
        while stack:
            node, path, on_path = stack.pop()
            for nxt in graph.get(node, ()):
                if nxt == start and len(path) > 1:
                    cycle = tuple(path)
                    rotated = min(cycle[i:] + cycle[:i] for i in range(len(cycle)))
                    if rotated not in found:
                        found.append(rotated)
                    continue
                if nxt in on_path or nxt in seen:
                    continue
                stack.append((nxt, path + [nxt], on_path | {nxt}))
        seen.add(start)
    return found


def _new_layer_cycles(diff, policy: Policy) -> List[Violation]:
    head = _graph(diff, ("added", "unchanged"))
    base_edges = {
        (imp.source, imp.target) for imp in diff.imports if imp.status in ("removed", "unchanged")
    }
    violations = []
    for cycle in _cycles(head):
        layers = {policy.layer_for(node) for node in cycle}
        layers.discard(None)
        if len(layers) < 2:
            continue
        edges = set(zip(cycle, cycle[1:] + cycle[:1]))
        if edges <= base_edges:
            continue
        joined = " \u2192 ".join(cycle)
        violations.append(Violation(
            kind="layer_cycle",
            message=f"Layer-crossing cycle {joined}",
            source=cycle[0],
            target=cycle[-1],
            is_new=True,
        ))
    return violations
