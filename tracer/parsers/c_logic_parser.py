"""C/C++ logic parser using libclang (clang.cindex).

Requires the 'libclang' Python package:
    pip install libclang

Falls back gracefully (returns None) if libclang is not installed.
"""

import os
from typing import List, Optional, Tuple

from ..logic import (
    FunctionBody, CallStmt, AssignStmt, ReturnStmt,
    BreakStmt, ContinueStmt,
    IfBlock, ForBlock, WhileBlock, SwitchBlock, SwitchCase,
)

try:
    import clang.cindex as cindex
    _CLANG_AVAILABLE = True
except ImportError:
    _CLANG_AVAILABLE = False


# ── Source-text helpers ────────────────────────────────────────────────────────

def _src(cursor, source_bytes: bytes) -> str:
    """Extract UTF-8 text for a cursor's byte-offset extent."""
    start = cursor.extent.start.offset
    end = cursor.extent.end.offset
    return source_bytes[start:end].decode("utf-8", errors="replace")


def _short(s: str, n: int = 50) -> str:
    s = " ".join(s.split())          # normalise whitespace
    return s if len(s) <= n else s[: n - 3] + "..."


# ── Call-expression helpers ────────────────────────────────────────────────────

def _find_call(cursor) -> Optional["cindex.Cursor"]:
    """Recursively find the first CALL_EXPR under *cursor*."""
    if not _CLANG_AVAILABLE:
        return None
    if cursor.kind == cindex.CursorKind.CALL_EXPR:
        return cursor
    for child in cursor.get_children():
        hit = _find_call(child)
        if hit:
            return hit
    return None


def _call_name(cursor) -> str:
    """Return the function name from a CALL_EXPR cursor."""
    spelling = cursor.spelling
    if spelling:
        return spelling
    children = list(cursor.get_children())
    if children and children[0].spelling:
        return children[0].spelling
    return "?"


def _call_args(cursor, source_bytes: bytes) -> List[str]:
    """Return argument texts from a CALL_EXPR cursor (skip the callee child)."""
    children = list(cursor.get_children())
    return [_short(_src(c, source_bytes), 25) for c in children[1:] if _src(c, source_bytes).strip()]


# ── Statement extractors ───────────────────────────────────────────────────────

def _extract_stmts(cursor, source_bytes: bytes) -> List:
    """Extract all statements from a COMPOUND_STMT (or a single non-compound cursor)."""
    if cursor is None:
        return []
    if cursor.kind == cindex.CursorKind.COMPOUND_STMT:
        result = []
        for child in cursor.get_children():
            result.extend(_extract_stmt(child, source_bytes))
        return result
    return _extract_stmt(cursor, source_bytes)


def _extract_if(cursor, source_bytes: bytes) -> IfBlock:
    """IF_STMT → IfBlock, unwrapping else-if chains."""
    children = list(cursor.get_children())
    if not children:
        return IfBlock(condition="?")

    cond_cursor = children[0]
    then_cursor = children[1] if len(children) > 1 else None
    else_cursor = children[2] if len(children) > 2 else None

    cond      = _short(_src(cond_cursor, source_bytes))
    then_body = _extract_stmts(then_cursor, source_bytes) if then_cursor else []

    elif_clauses: List[Tuple[str, List]] = []
    else_body: List = []

    # Unwrap else-if chain
    while else_cursor and else_cursor.kind == cindex.CursorKind.IF_STMT:
        ec = list(else_cursor.get_children())
        elif_cond = _short(_src(ec[0], source_bytes)) if ec else "?"
        elif_then = _extract_stmts(ec[1], source_bytes) if len(ec) > 1 else []
        elif_clauses.append((elif_cond, elif_then))
        else_cursor = ec[2] if len(ec) > 2 else None

    if else_cursor:
        else_body = _extract_stmts(else_cursor, source_bytes)

    return IfBlock(condition=cond, then_body=then_body,
                   elif_clauses=elif_clauses, else_body=else_body)


def _extract_for(cursor, source_bytes: bytes) -> WhileBlock:
    """FOR_STMT → WhileBlock.

    The body is always the last child.  Everything before the body's opening
    brace is the loop header (init; condition; increment), used as condition text.
    """
    children = list(cursor.get_children())
    body_cursor = children[-1] if children else None

    full_src = _src(cursor, source_bytes)
    if body_cursor:
        # Byte offset of body start relative to this cursor's start
        rel = body_cursor.extent.start.offset - cursor.extent.start.offset
        header = full_src[:rel].strip()
    else:
        header = full_src[:60]

    body = _extract_stmts(body_cursor, source_bytes) if body_cursor else []
    return WhileBlock(condition=_short(header), body=body)


def _extract_while(cursor, source_bytes: bytes) -> WhileBlock:
    """WHILE_STMT → WhileBlock."""
    children = list(cursor.get_children())
    cond_cursor = children[0] if children else None
    body_cursor = children[1] if len(children) > 1 else None

    cond = _short(_src(cond_cursor, source_bytes)) if cond_cursor else "?"
    body = _extract_stmts(body_cursor, source_bytes) if body_cursor else []
    return WhileBlock(condition=cond, body=body)


def _extract_do_while(cursor, source_bytes: bytes) -> WhileBlock:
    """DO_STMT → WhileBlock (body first, condition at end)."""
    children = list(cursor.get_children())
    body_cursor = children[0] if children else None
    cond_cursor = children[1] if len(children) > 1 else None

    cond = _short(_src(cond_cursor, source_bytes)) if cond_cursor else "?"
    body = _extract_stmts(body_cursor, source_bytes) if body_cursor else []
    return WhileBlock(condition=f"do-while: {cond}", body=body)


def _extract_switch(cursor, source_bytes: bytes) -> SwitchBlock:
    """SWITCH_STMT → SwitchBlock."""
    children = list(cursor.get_children())
    subject_cursor = children[0] if children else None
    body_cursor    = children[1] if len(children) > 1 else None

    subject = _short(_src(subject_cursor, source_bytes)) if subject_cursor else "?"
    cases: List[SwitchCase] = []

    if body_cursor and body_cursor.kind == cindex.CursorKind.COMPOUND_STMT:
        cur_patterns: List[str] = []
        cur_body: List = []
        is_default = False

        for child in body_cursor.get_children():
            if child.kind == cindex.CursorKind.CASE_STMT:
                if cur_patterns or is_default:
                    pat = " / ".join(cur_patterns) if cur_patterns else "_"
                    cases.append(SwitchCase(pattern=pat, body=cur_body, is_default=is_default))
                cc = list(child.get_children())
                pat_text = _short(_src(cc[0], source_bytes)) if cc else "?"
                cur_patterns = [pat_text]
                cur_body = _extract_stmts(cc[1], source_bytes) if len(cc) > 1 else []
                is_default = False

            elif child.kind == cindex.CursorKind.DEFAULT_STMT:
                if cur_patterns or is_default:
                    pat = " / ".join(cur_patterns) if cur_patterns else "_"
                    cases.append(SwitchCase(pattern=pat, body=cur_body, is_default=is_default))
                dc = list(child.get_children())
                cur_body = _extract_stmts(dc[0], source_bytes) if dc else []
                cur_patterns = []
                is_default = True

            else:
                cur_body.extend(_extract_stmt(child, source_bytes))

        if cur_patterns or is_default:
            pat = " / ".join(cur_patterns) if cur_patterns else "_"
            cases.append(SwitchCase(pattern=pat, body=cur_body, is_default=is_default))

    return SwitchBlock(subject=subject, cases=cases)


def _extract_decl_stmt(cursor, source_bytes: bytes) -> List:
    """DECL_STMT → CallStmt (if initializer is a call) or AssignStmt."""
    result = []
    for child in cursor.get_children():
        if child.kind == cindex.CursorKind.VAR_DECL:
            var_name = child.spelling
            init_children = list(child.get_children())
            if not init_children:
                continue
            call = _find_call(init_children[0])
            if call:
                result.append(CallStmt(
                    name=_call_name(call),
                    args=_call_args(call, source_bytes),
                    assigned_to=var_name,
                ))
            else:
                val = _short(_src(init_children[0], source_bytes))
                result.append(AssignStmt(target=var_name, value=val))
    return result


def _extract_stmt(cursor, source_bytes: bytes) -> List:  # noqa: C901
    """Dispatch a single cursor to the appropriate extractor."""
    k = cursor.kind

    if k == cindex.CursorKind.COMPOUND_STMT:
        return _extract_stmts(cursor, source_bytes)

    if k == cindex.CursorKind.IF_STMT:
        return [_extract_if(cursor, source_bytes)]

    if k == cindex.CursorKind.FOR_STMT:
        return [_extract_for(cursor, source_bytes)]

    if k == cindex.CursorKind.WHILE_STMT:
        return [_extract_while(cursor, source_bytes)]

    if k == cindex.CursorKind.DO_STMT:
        return [_extract_do_while(cursor, source_bytes)]

    if k == cindex.CursorKind.SWITCH_STMT:
        return [_extract_switch(cursor, source_bytes)]

    if k == cindex.CursorKind.BREAK_STMT:
        return [BreakStmt()]

    if k == cindex.CursorKind.CONTINUE_STMT:
        return [ContinueStmt()]

    if k == cindex.CursorKind.RETURN_STMT:
        children = list(cursor.get_children())
        val = _short(_src(children[0], source_bytes)) if children else ""
        return [ReturnStmt(value=val)]

    if k == cindex.CursorKind.CALL_EXPR:
        return [CallStmt(name=_call_name(cursor), args=_call_args(cursor, source_bytes))]

    if k == cindex.CursorKind.DECL_STMT:
        return _extract_decl_stmt(cursor, source_bytes)

    if k in (
        cindex.CursorKind.BINARY_OPERATOR,
        cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
    ):
        children = list(cursor.get_children())
        if len(children) >= 2:
            call = _find_call(children[1])
            if call:
                target = _short(_src(children[0], source_bytes), 30)
                return [CallStmt(name=_call_name(call),
                                 args=_call_args(call, source_bytes),
                                 assigned_to=target)]
            target = _short(_src(children[0], source_bytes), 30)
            val    = _short(_src(children[1], source_bytes), 35)
            return [AssignStmt(target=target, value=val)]
        return []

    if k in (cindex.CursorKind.UNEXPOSED_STMT, cindex.CursorKind.UNEXPOSED_EXPR):
        result = []
        for child in cursor.get_children():
            result.extend(_extract_stmt(child, source_bytes))
        return result

    return []


# ── Function finder ────────────────────────────────────────────────────────────

def _find_func_cursor(root_cursor, qualified_name: str, target_file: str):
    """Return the definition cursor for *qualified_name* inside *target_file*."""
    norm_target = os.path.normcase(os.path.abspath(target_file))

    parts     = qualified_name.replace("::", ".").split(".")
    func_name = parts[-1]
    class_name = parts[-2] if len(parts) >= 2 else None

    _class_kinds = (
        cindex.CursorKind.CLASS_DECL,
        cindex.CursorKind.STRUCT_DECL,
        cindex.CursorKind.CLASS_TEMPLATE,
    )
    _func_kinds = (
        cindex.CursorKind.FUNCTION_DECL,
        cindex.CursorKind.CXX_METHOD,
        cindex.CursorKind.FUNCTION_TEMPLATE,
    )

    def _in_file(cursor) -> bool:
        loc = cursor.location
        if not loc.file:
            return False
        return os.path.normcase(os.path.abspath(loc.file.name)) == norm_target

    def _walk(cursor):
        for child in cursor.get_children():
            if not _in_file(child):
                # Still descend into namespaces / translation unit children
                if child.kind in (cindex.CursorKind.NAMESPACE,
                                  cindex.CursorKind.TRANSLATION_UNIT):
                    hit = _walk(child)
                    if hit:
                        return hit
                continue

            if class_name and child.kind in _class_kinds and child.spelling == class_name:
                hit = _search_class(child)
                if hit:
                    return hit

            if (not class_name
                    and child.kind in _func_kinds
                    and child.spelling == func_name
                    and child.is_definition()):
                return child

            hit = _walk(child)
            if hit:
                return hit
        return None

    def _search_class(class_cursor):
        for child in class_cursor.get_children():
            if (child.kind == cindex.CursorKind.CXX_METHOD
                    and child.spelling == func_name
                    and child.is_definition()):
                return child
        return None

    return _walk(root_cursor)


# ── Public parser class ────────────────────────────────────────────────────────

class CLogicParser:
    """Extract FunctionBody (internal logic) from a C/C++ file via libclang."""

    def __init__(self, extra_args: Optional[List[str]] = None):
        self._extra_args = extra_args or []

    @staticmethod
    def available() -> bool:
        return _CLANG_AVAILABLE

    def parse_function(self, file_path: str, qualified_name: str) -> Optional[FunctionBody]:
        """Return FunctionBody for *qualified_name* in *file_path*, or None."""
        if not _CLANG_AVAILABLE:
            return None

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".cpp", ".cxx", ".cc", ".hpp", ".hxx"):
                base_args = ["-std=c++17", "-x", "c++"]
            else:
                base_args = ["-std=c11", "-x", "c"]

            args = base_args + self._extra_args

            idx = cindex.Index.create()
            tu  = idx.parse(
                file_path,
                args=args,
                options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
            )

            with open(file_path, "rb") as fh:
                source_bytes = fh.read()

            func_cursor = _find_func_cursor(tu.cursor, qualified_name, file_path)
            if func_cursor is None:
                return None

            # The body is the COMPOUND_STMT child of the function
            body_cursor = None
            for child in func_cursor.get_children():
                if child.kind == cindex.CursorKind.COMPOUND_STMT:
                    body_cursor = child
                    break

            if body_cursor is None:
                return None

            params = [p.spelling for p in func_cursor.get_arguments()]
            stmts  = _extract_stmts(body_cursor, source_bytes)

            return FunctionBody(
                qualified_name=qualified_name,
                file=os.path.abspath(file_path),
                line=func_cursor.location.line,
                language="c/c++",
                params=params,
                statements=stmts,
            )

        except Exception:
            return None
