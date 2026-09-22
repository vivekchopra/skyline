"""Extract the generic structural model (see model.py) from Python source
using the standard-library ``ast`` module. No third-party dependencies, no
execution of the target code.
"""
from __future__ import annotations

import ast
from typing import List, Optional

from .model import FunctionEntity, Member, ModuleModel, TypeEntity


def _unparse(node) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _decorator_names(decorator_list) -> List[str]:
    names = []
    for d in decorator_list:
        try:
            names.append(ast.unparse(d))
        except Exception:
            names.append("?")
    return names


def _args_list(args: ast.arguments) -> List[str]:
    out: List[str] = []
    for a in args.posonlyargs:
        out.append(a.arg)
    for a in args.args:
        out.append(a.arg)
    if args.vararg:
        out.append(f"*{args.vararg.arg}")
    for a in args.kwonlyargs:
        out.append(a.arg)
    if args.kwarg:
        out.append(f"**{args.kwarg.arg}")
    return out


def _modifiers(node) -> List[str]:
    mods = _decorator_names(node.decorator_list)
    if isinstance(node, ast.AsyncFunctionDef):
        mods.append("async")
    return mods


def _returns(node) -> Optional[str]:
    return _unparse(node.returns) or None


class _ComplexityVisitor(ast.NodeVisitor):
    """Cyclomatic complexity: 1 + one per decision point. Does not descend
    into nested function/class defs -- each unit's complexity stays scoped
    to itself, matching how it's reported as a separate Member/FunctionEntity
    elsewhere (a nested def inside a method isn't extracted as its own
    member, so double-counting its branches into the parent would be
    confusing, not more accurate)."""

    def __init__(self):
        self.complexity = 1

    def _branch(self, node):
        self.complexity += 1
        self.generic_visit(node)

    visit_If = _branch
    visit_For = _branch
    visit_AsyncFor = _branch
    visit_While = _branch
    visit_ExceptHandler = _branch
    visit_IfExp = _branch  # ternary
    visit_match_case = _branch

    def visit_BoolOp(self, node):
        self.complexity += max(len(node.values) - 1, 0)
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.complexity += 1 + len(node.ifs)
        self.generic_visit(node)

    def _skip(self, node):
        return  # don't descend into nested function/class units

    visit_FunctionDef = _skip
    visit_AsyncFunctionDef = _skip
    visit_ClassDef = _skip
    visit_Lambda = _skip


def _complexity(body) -> int:
    visitor = _ComplexityVisitor()
    for stmt in body:
        visitor.visit(stmt)
    return visitor.complexity


def extract_module(path: str, source: str) -> ModuleModel:
    """Parse ``source`` (the contents of a .py file) into a ModuleModel.

    Unparseable files (e.g. Python 2, syntax errors) yield an empty
    module rather than raising, so a single bad file in a PR doesn't
    crash the whole report.
    """
    module = ModuleModel(path=path, language="python")
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return module

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [b for b in (_unparse(b) for b in node.bases) if b]
            qualname = f"{path}::{node.name}"
            type_entity = TypeEntity(
                name=node.name,
                qualname=qualname,
                kind="class",
                decorators=_decorator_names(node.decorator_list),
                relations=[(b, "extends") for b in bases],
                exported=True,
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    type_entity.members[item.name] = Member(
                        name=item.name,
                        kind="method",
                        params=_args_list(item.args),
                        modifiers=_modifiers(item),
                        return_type=_returns(item),
                        complexity=_complexity(item.body),
                    )
            module.types[node.name] = type_entity
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{path}::{node.name}"
            module.functions[node.name] = FunctionEntity(
                name=node.name,
                qualname=qualname,
                params=_args_list(node.args),
                modifiers=_modifiers(node),
                return_type=_returns(node),
                exported=True,
                complexity=_complexity(node.body),
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                module.imports.append(f"{mod}.{alias.name}" if mod else alias.name)

    return module
