"""Extract internal logic structure from a Python function using the AST.

Extraction checklist
--------------------
[x] Plain call:            foo(a, b)
[x] Assigned call:         result = foo(a, b)
[x] Non-call assignment:   x = 5  /  x = [1,2]  /  items = some_list
[x] Augmented assignment:  x += 1  (non-call)
[x] return
[x] raise
[x] assert condition, msg
[x] break
[x] continue
[x] if / elif / else   (condition extracted from ast.If.test)
[x] for loop           (target + iterable extracted)
[x] while loop         (condition extracted)
[x] try / except (multi-handler) / finally
[x] match / case       (Python 3.10+, guarded with hasattr)
"""

import ast
import os
from typing import List, Optional, Tuple

from ..logic import (
    FunctionBody, CallStmt, AssignStmt, ReturnStmt, RaiseStmt,
    AssertStmt, BreakStmt, ContinueStmt,
    IfBlock, ForBlock, WhileBlock, TryBlock,
    SwitchBlock, SwitchCase,
)


# ── AST helpers ───────────────────────────────────────────────────────────────

def _unparse(node) -> str:
    """Convert an AST expression to a string."""
    if node is None:
        return "None"
    try:
        return ast.unparse(node)           # Python 3.9+
    except AttributeError:
        return _fallback_unparse(node)     # Python 3.8
    except Exception:
        return "..."


def _fallback_unparse(node) -> str:
    """Minimal expression → string for Python 3.8."""
    if node is None:
        return "None"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_fallback_unparse(node.value)}.{node.attr}"
    if isinstance(node, ast.Constant):
        s = repr(node.value)
        return s[:30] if len(s) > 30 else s
    if isinstance(node, ast.Call):
        return f"{_fallback_unparse(node.func)}(...)"
    if isinstance(node, ast.Compare):
        ops = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
               ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
               ast.In: "in", ast.NotIn: "not in"}
        op_str = ops.get(type(node.ops[0]), "?") if node.ops else "?"
        return f"{_fallback_unparse(node.left)} {op_str} ..."
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        parts = [_fallback_unparse(v) for v in node.values[:2]]
        return f" {op} ".join(parts)
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return f"not {_fallback_unparse(node.operand)}"
        if isinstance(node.op, ast.USub):
            return f"-{_fallback_unparse(node.operand)}"
    if isinstance(node, ast.Subscript):
        return f"{_fallback_unparse(node.value)}[...]"
    if isinstance(node, (ast.Tuple, ast.List)):
        elts = [_fallback_unparse(e) for e in node.elts[:2]]
        suffix = ", ..." if len(node.elts) > 2 else ""
        return f"({', '.join(elts)}{suffix})"
    if isinstance(node, ast.IfExp):
        return f"{_fallback_unparse(node.body)} if ... else ..."
    return type(node).__name__


def _short(s: str, n: int = 45) -> str:
    return s if len(s) <= n else s[:n - 3] + "..."


def _call_name(node: ast.Call) -> Optional[str]:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _call_args(node: ast.Call) -> List[str]:
    args = [_short(_unparse(a), 25) for a in node.args]
    for kw in node.keywords:
        if kw.arg:
            args.append(f"{kw.arg}={_short(_unparse(kw.value), 15)}")
        else:
            args.append(f"**{_short(_unparse(kw.value), 15)}")
    return args


def _target_str(target_node) -> str:
    """Convert an assignment target node to a string."""
    return _short(_unparse(target_node), 30)


# ── Statement extraction ───────────────────────────────────────────────────────

def _extract_stmts(stmts) -> List:
    out = []
    for s in stmts:
        out.extend(_extract_stmt(s))
    return out


def _extract_stmt(stmt) -> List:  # noqa: C901  (complexity OK for exhaustive dispatch)

    # ── [x] Plain call: foo(...)
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        name = _call_name(stmt.value)
        if name:
            return [CallStmt(name=name, args=_call_args(stmt.value))]

    # ── [x] Assignment: x = expr  /  x: T = expr
    elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        if isinstance(stmt, ast.Assign):
            val = stmt.value
            tgt = _target_str(stmt.targets[0]) if stmt.targets else "?"
        else:  # AnnAssign
            val = getattr(stmt, "value", None)
            tgt = _target_str(stmt.target)

        if val is None:
            return []  # bare annotation: x: int  (no value)
        if isinstance(val, ast.Call):
            name = _call_name(val)
            if name:
                return [CallStmt(name=name, args=_call_args(val), assigned_to=tgt)]
        # Non-call assignment → AssignStmt
        return [AssignStmt(target=tgt, value=_short(_unparse(val), 35))]

    # ── [x] Augmented assignment: x += expr
    elif isinstance(stmt, ast.AugAssign):
        val = stmt.value
        tgt = _target_str(stmt.target)
        if isinstance(val, ast.Call):
            name = _call_name(val)
            if name:
                return [CallStmt(name=name, args=_call_args(val), assigned_to=tgt)]
        # Build "x op= val" representation
        op_map = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
            ast.BitOr: "|", ast.BitAnd: "&", ast.BitXor: "^",
        }
        op = op_map.get(type(stmt.op), "op")
        return [AssignStmt(target=tgt, value=f"{tgt} {op}= {_short(_unparse(val), 20)}")]

    # ── [x] return
    elif isinstance(stmt, ast.Return):
        val = _short(_unparse(stmt.value)) if stmt.value else ""
        return [ReturnStmt(value=val)]

    # ── [x] raise
    elif isinstance(stmt, ast.Raise):
        exc = _short(_unparse(stmt.exc)) if stmt.exc else ""
        return [RaiseStmt(exc=exc)]

    # ── [x] assert condition, message
    elif isinstance(stmt, ast.Assert):
        cond = _short(_unparse(stmt.test))
        msg = _short(_unparse(stmt.msg)) if stmt.msg else ""
        return [AssertStmt(condition=cond, msg=msg)]

    # ── [x] break
    elif isinstance(stmt, ast.Break):
        return [BreakStmt()]

    # ── [x] continue
    elif isinstance(stmt, ast.Continue):
        return [ContinueStmt()]

    # ── [x] if / elif / else
    elif isinstance(stmt, ast.If):
        cond = _short(_unparse(stmt.test))
        then = _extract_stmts(stmt.body)
        elif_clauses: List[Tuple[str, List]] = []
        else_body: List = []
        orelse = stmt.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                n = orelse[0]
                elif_clauses.append((_short(_unparse(n.test)), _extract_stmts(n.body)))
                orelse = n.orelse
            else:
                else_body = _extract_stmts(orelse)
                break
        return [IfBlock(condition=cond, then_body=then,
                        elif_clauses=elif_clauses, else_body=else_body)]

    # ── [x] for loop
    elif isinstance(stmt, ast.For):
        target = _short(_unparse(stmt.target))
        iterable = _short(_unparse(stmt.iter))
        return [ForBlock(target=target, iterable=iterable,
                         body=_extract_stmts(stmt.body))]

    # ── [x] while loop
    elif isinstance(stmt, ast.While):
        cond = _short(_unparse(stmt.test))
        return [WhileBlock(condition=cond, body=_extract_stmts(stmt.body))]

    # ── [x] try / except / finally
    elif isinstance(stmt, ast.Try):
        body = _extract_stmts(stmt.body)
        handlers = []
        for h in stmt.handlers:
            exc_type = _short(_unparse(h.type)) if h.type else "Exception"
            handlers.append((exc_type, _extract_stmts(h.body)))
        finally_body = _extract_stmts(stmt.finalbody) if stmt.finalbody else []
        return [TryBlock(body=body, handlers=handlers, finally_body=finally_body)]

    # ── [x] match / case (Python 3.10+)
    elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
        subject = _short(_unparse(stmt.subject))
        cases = []
        for case in stmt.cases:
            pattern = _short(_unparse(case.pattern))
            is_default = (isinstance(case.pattern, ast.MatchAs)
                          and case.pattern.name is None)
            body = _extract_stmts(case.body)
            cases.append(SwitchCase(pattern=pattern, body=body, is_default=is_default))
        return [SwitchBlock(subject=subject, cases=cases)]

    return []


# ── Main parser class ──────────────────────────────────────────────────────────

class PythonLogicParser:
    """Extract FunctionBody (internal logic) from a Python source file."""

    def parse_function(self, file_path: str, qualified_name: str) -> Optional[FunctionBody]:
        """Return FunctionBody for `qualified_name` in `file_path`, or None."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            tree = ast.parse(source, filename=file_path)
        except (OSError, SyntaxError):
            return None

        found = self._find_function(tree, qualified_name)
        if not found:
            return None

        func_node, params = found
        return FunctionBody(
            qualified_name=qualified_name,
            file=os.path.abspath(file_path),
            line=func_node.lineno,
            language="python",
            params=params,
            statements=_extract_stmts(func_node.body),
        )

    def _find_function(self, tree, qualified_name: str):
        """Find the AST FunctionDef node matching `qualified_name`."""
        parts = qualified_name.split(".", 1)
        class_name = parts[0] if len(parts) == 2 else None
        func_name = parts[1] if len(parts) == 2 else parts[0]

        for node in ast.walk(tree):
            if class_name:
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for child in node.body:
                        if (isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                                and child.name == func_name):
                            return child, self._params(child)
            else:
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name == func_name):
                    return node, self._params(node)
        return None

    def _params(self, node) -> List[str]:
        args = node.args
        params = [a.arg for a in args.args if a.arg not in ("self", "cls")]
        if args.vararg:
            params.append(f"*{args.vararg.arg}")
        params += [f"{a.arg}=..." for a in args.kwonlyargs]
        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")
        return params
