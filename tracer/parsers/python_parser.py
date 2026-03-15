"""Python source parser using the built-in `ast` module."""

import ast
import os
from typing import List, Optional, Tuple

from ..graph import FunctionNode
from .base_parser import BaseParser


def _unparse(node) -> str:
    if node is None:
        return "None"
    try:
        return ast.unparse(node)       # Python 3.9+
    except AttributeError:
        return _fallback_unparse(node)
    except Exception:
        return "..."


def _fallback_unparse(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_fallback_unparse(node.value)}.{node.attr}"
    if isinstance(node, ast.Constant):
        s = repr(node.value)
        return s[:25] if len(s) > 25 else s
    if isinstance(node, ast.Call):
        return f"{_fallback_unparse(node.func)}(...)"
    return type(node).__name__


def _short(s: str, n: int = 25) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."


class _CallVisitor(ast.NodeVisitor):
    """Collect all function/method call names (and args) within a node."""

    def __init__(self):
        self.calls: List[str] = []
        self.call_sites: List[Tuple[str, List[str]]] = []

    def visit_Call(self, node: ast.Call):
        name = self._extract_name(node.func)
        if name:
            self.calls.append(name)
            args = self._extract_args(node)
            self.call_sites.append((name, args))
        self.generic_visit(node)

    @staticmethod
    def _extract_name(node) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    @staticmethod
    def _extract_args(node: ast.Call) -> List[str]:
        args = [_short(_unparse(a)) for a in node.args]
        for kw in node.keywords:
            if kw.arg:
                args.append(f"{kw.arg}={_short(_unparse(kw.value), 15)}")
            else:
                args.append(f"**{_short(_unparse(kw.value), 15)}")
        return args


class _FunctionVisitor(ast.NodeVisitor):
    """Walk the AST and extract all function/method definitions."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.nodes: List[FunctionNode] = []
        self._class_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._process_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._process_func(node)

    def _process_func(self, node):
        func_name = node.name
        class_name = self._class_stack[-1] if self._class_stack else None
        qualified = f"{class_name}.{func_name}" if class_name else func_name

        visitor = _CallVisitor()
        visitor.visit(node)

        fn = FunctionNode(
            name=func_name,
            qualified_name=qualified,
            file=self.file_path,
            line=node.lineno,
            language="python",
            calls=visitor.calls,
            call_sites=visitor.call_sites,
        )
        self.nodes.append(fn)

        saved = list(self._class_stack)
        for child in ast.iter_child_nodes(node):
            self.visit(child)
        self._class_stack = saved


class PythonParser(BaseParser):
    def parse(self, file_path: str) -> List[FunctionNode]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            return []

        visitor = _FunctionVisitor(os.path.abspath(file_path))
        visitor.visit(tree)
        return visitor.nodes
