"""C / C++ parser (regex-based)."""

import os
import re
from typing import List

from ..graph import FunctionNode
from .base_parser import BaseParser

# Match function definitions: return_type func_name(params) {
# Heuristic: line starts with optional type, then identifier, then '('
_FUNC_DEF_PATTERN = re.compile(
    r"^"
    r"(?:(?:static|inline|extern|const|virtual|override|explicit|"
    r"__attribute__\s*\([^)]*\)|[\w:*&<>, \t]+?)\s+)?"  # optional specifiers / return type
    r"(~?\w+(?:::\w+)?)"   # function name (optionally qualified)
    r"\s*\("               # open paren
    r"[^;{]*"              # params (no semicolons, no body yet)
    r"\)\s*(?:const\s*)?(?:noexcept\s*)?"  # optional const/noexcept
    r"(?:override\s*)?"
    r"\s*\{",              # opening brace (definition, not declaration)
    re.MULTILINE,
)

_CALL_PATTERN = re.compile(r"\b(\w+)\s*\(")

_SKIP_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "do", "catch", "return",
    "sizeof", "typeof", "alignof", "new", "delete", "throw",
    "static_cast", "dynamic_cast", "reinterpret_cast", "const_cast",
    "assert", "ASSERT", "CHECK",
})


def _find_functions(source: str, file_path: str) -> List[FunctionNode]:
    nodes: List[FunctionNode] = []
    seen: set = set()

    all_matches = []
    for m in _FUNC_DEF_PATTERN.finditer(source):
        name = m.group(1)
        # Skip things that look like control flow or type casts
        if name in _SKIP_KEYWORDS:
            continue
        line_no = source[:m.start()].count("\n")
        pos = (line_no, name)
        if pos not in seen:
            seen.add(pos)
            all_matches.append((line_no, name, m.start(), m.end()))

    all_matches.sort(key=lambda x: x[0])

    for idx, (line_no, name, start_pos, end_pos) in enumerate(all_matches):
        # Determine class from qualified name  e.g. MyClass::foo
        if "::" in name:
            parts = name.split("::")
            class_name = "::".join(parts[:-1])
            func_name = parts[-1]
        else:
            class_name = ""
            func_name = name
        qualified = name  # already qualified for C++

        brace_start = source.find("{", end_pos - 1)
        if brace_start == -1:
            body = ""
        else:
            next_start = all_matches[idx + 1][2] if idx + 1 < len(all_matches) else len(source)
            body = source[brace_start:min(next_start, len(source))]

        calls = list({m.group(1) for m in _CALL_PATTERN.finditer(body)
                      if m.group(1) not in _SKIP_KEYWORDS})

        node = FunctionNode(
            name=func_name,
            qualified_name=qualified,
            file=os.path.abspath(file_path),
            line=line_no + 1,
            language="c/c++",
            calls=calls,
        )
        nodes.append(node)

    return nodes


class CParser(BaseParser):
    def parse(self, file_path: str) -> List[FunctionNode]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        return _find_functions(source, file_path)
