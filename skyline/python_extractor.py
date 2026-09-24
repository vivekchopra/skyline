"""Extract the generic structural model (see model.py) from Python source
using the standard-library ``ast`` module. No third-party dependencies, no
execution of the target code.
"""
from __future__ import annotations

import ast
import hashlib
from typing import List, Optional

from .model import Column, FunctionEntity, Member, ModuleModel, Table, TypeEntity

_NESTED_UNITS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


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


def _body_hash(body) -> str:
    """Hash this unit's own statements. Nested defs are separate units, so
    they are left out of the parent hash."""
    parts = [_unparse(stmt) for stmt in body if not isinstance(stmt, _NESTED_UNITS)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _exported_name(name: str) -> bool:
    """Leading underscore is internal. Dunder names such as ``__init__`` stay public."""
    if name.startswith("__") and name.endswith("__") and len(name) > 4:
        return True
    return not name.startswith("_")


def _is_django_model(bases: List[str]) -> bool:
    return any(base == "Model" or base.endswith(".Model") for base in bases)


def _column_from_call(name: str, value) -> Optional[tuple]:
    """Return (name, type, relation, is_sqlalchemy) for a field assignment."""
    if not isinstance(value, ast.Call):
        return None
    func = _unparse(value.func)
    tail = func.split(".")[-1]
    is_django = tail.endswith("Field") or tail in ("ForeignKey", "ManyToManyField", "OneToOneField")
    is_sqlalchemy = tail in ("Column", "mapped_column")
    if not is_django and not is_sqlalchemy:
        return None
    relation = None
    if tail in ("ForeignKey", "ManyToManyField", "OneToOneField") and value.args:
        relation = _unparse(value.args[0])
    return name, tail, relation, is_sqlalchemy


def _string_constant(node) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_table(path: str, node: ast.ClassDef, bases: List[str]) -> Optional[Table]:
    django = _is_django_model(bases)
    sqlalchemy = False
    tablename = node.name
    columns: dict = {}
    relations: List[str] = []

    for item in node.body:
        if isinstance(item, ast.ClassDef) and item.name == "Meta":
            for meta_item in item.body:
                if isinstance(meta_item, ast.Assign):
                    for target in meta_item.targets:
                        if isinstance(target, ast.Name) and target.id == "db_table":
                            text = _string_constant(meta_item.value)
                            if text:
                                tablename = text
            continue
        targets = []
        value = None
        if isinstance(item, ast.Assign):
            targets = [t.id for t in item.targets if isinstance(t, ast.Name)]
            value = item.value
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            targets = [item.target.id]
            value = item.value
        for target_name in targets:
            if target_name == "__tablename__":
                text = _string_constant(value) if value is not None else None
                if text:
                    tablename = text
                    sqlalchemy = True
                continue
            if value is not None:
                parsed = _column_from_call(target_name, value)
                if parsed:
                    col_name, col_type, relation, is_sa = parsed
                    sqlalchemy = sqlalchemy or is_sa
                    columns[col_name] = Column(name=col_name, type=col_type)
                    if relation:
                        relations.append(relation)
                    continue
            if isinstance(item, ast.AnnAssign):
                annotation = _unparse(item.annotation)
                if "Mapped" in annotation:
                    sqlalchemy = True
                    columns[target_name] = Column(name=target_name, type=annotation)
    if not django and not sqlalchemy:
        return None
    return Table(
        name=tablename,
        qualname=f"{path}::{tablename}",
        path=path,
        columns=columns,
        relations=relations,
    )


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
                exported=_exported_name(node.name),
                line=node.lineno,
                end_line=node.end_lineno,
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
                        body_hash=_body_hash(item.body),
                        exported=_exported_name(item.name),
                        line=item.lineno,
                        end_line=item.end_lineno,
                    )
            module.types[node.name] = type_entity
            table = _extract_table(path, node, bases)
            if table is not None:
                module.tables[table.name] = table
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{path}::{node.name}"
            module.functions[node.name] = FunctionEntity(
                name=node.name,
                qualname=qualname,
                params=_args_list(node.args),
                modifiers=_modifiers(node),
                return_type=_returns(node),
                exported=_exported_name(node.name),
                complexity=_complexity(node.body),
                body_hash=_body_hash(node.body),
                line=node.lineno,
                end_line=node.end_lineno,
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in module.imports:
                    module.imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            dots = "." * node.level
            mod = node.module or ""
            spec = f"{dots}{mod}" if (dots or mod) else ""
            if spec and spec not in module.imports:
                module.imports.append(spec)

    return module
