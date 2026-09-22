"""Language-agnostic structural model.

Every language extractor (Python's ``ast``-based one, TypeScript's
compiler-API-based one, and any future one) produces these same
dataclasses, so the diff engine and renderers never need to know which
language they're looking at.

A "relation" is a (target_name, kind) pair where kind is ``"extends"``
(inheritance / a solid UML arrow) or ``"implements"`` (interface
realization / a dashed UML arrow). Python only ever produces ``"extends"``
relations (base classes); TypeScript produces both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Relation = Tuple[str, str]  # (target_name, "extends" | "implements")


@dataclass
class Member:
    """A method or property/field on a class or interface."""
    name: str
    kind: str  # "method" | "property"
    params: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)  # decorators, visibility, static, async, ...
    return_type: Optional[str] = None
    optional: bool = False
    complexity: Optional[int] = None  # cyclomatic complexity; None for signature-only members (e.g. interface methods)


@dataclass
class FunctionEntity:
    """A module-level (free) function."""
    name: str
    qualname: str
    params: List[str] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    exported: bool = True
    complexity: Optional[int] = None


@dataclass
class TypeEntity:
    """A class or interface."""
    name: str
    qualname: str
    kind: str  # "class" | "interface"
    decorators: List[str] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    members: Dict[str, Member] = field(default_factory=dict)
    exported: bool = True


@dataclass
class ModuleModel:
    path: str
    language: str  # "python" | "typescript"
    types: Dict[str, TypeEntity] = field(default_factory=dict)
    functions: Dict[str, FunctionEntity] = field(default_factory=dict)
    imports: List[str] = field(default_factory=list)
