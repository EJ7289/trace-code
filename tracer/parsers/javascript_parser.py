"""JavaScript / TypeScript parser (regex-based)."""

import os
import re
from typing import List

from ..graph import FunctionNode
from .base_parser import BaseParser

# Patterns to detect function definitions
_FUNC_PATTERNS = [
    # function foo(...)  /  async function foo(...)
    re.compile(r"(?:async\s+)?function\s+(\w+)\s*\("),
    # const foo = (...) =>  /  const foo = function(...)
    re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)"),
    # foo(...) { — method shorthand in class/object
    re.compile(r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{", re.MULTILINE),
    # Arrow method in class: foo = async (...) =>
    re.compile(r"(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>"),
]

# Pattern for function/method calls
_CALL_PATTERN = re.compile(r"\b(\w+)\s*\(")

# Pattern for class definition
_CLASS_PATTERN = re.compile(r"class\s+(\w+)")


def _find_functions(source: str, file_path: str) -> List[FunctionNode]:
    lines = source.splitlines()
    nodes: List[FunctionNode] = []
    seen_positions: set = set()

    # Simple pass: find class context for each line
    class_at_line: List[str] = [""] * len(lines)
    current_class = ""
    brace_depth = 0
    class_start_depth = -1

    for i, line in enumerate(lines):
        class_match = _CLASS_PATTERN.search(line)
        if class_match:
            current_class = class_match.group(1)
            class_start_depth = brace_depth
        brace_depth += line.count("{") - line.count("}")
        class_at_line[i] = current_class
        if current_class and brace_depth <= class_start_depth:
            current_class = ""
            class_start_depth = -1

    # Detect function definitions
    all_matches = []
    for pattern in _FUNC_PATTERNS:
        for m in pattern.finditer(source):
            name = m.group(1)
            line_no = source[:m.start()].count("\n")
            pos = (line_no, name)
            if pos not in seen_positions:
                seen_positions.add(pos)
                all_matches.append((line_no, name, m.start(), m.end()))

    # Sort by line number
    all_matches.sort(key=lambda x: x[0])

    # For each function, determine its body (heuristic: scan braces until balanced)
    for idx, (line_no, name, start_pos, end_pos) in enumerate(all_matches):
        class_name = class_at_line[line_no] if line_no < len(class_at_line) else ""
        qualified = f"{class_name}.{name}" if class_name else name

        # Find opening brace after match
        brace_start = source.find("{", end_pos)
        if brace_start == -1:
            body = ""
        else:
            # Determine next function start as body boundary
            next_start = all_matches[idx + 1][2] if idx + 1 < len(all_matches) else len(source)
            body_end = min(next_start, len(source))
            body = source[brace_start:body_end]

        calls = list({m.group(1) for m in _CALL_PATTERN.finditer(body)
                      if m.group(1) not in ("if", "for", "while", "switch",
                                             "catch", "function", "return",
                                             "typeof", "instanceof", "new",
                                             "class", "import", "require")})

        node = FunctionNode(
            name=name,
            qualified_name=qualified,
            file=os.path.abspath(file_path),
            line=line_no + 1,
            language="javascript",
            calls=calls,
        )
        nodes.append(node)

    return nodes


class JavaScriptParser(BaseParser):
    def parse(self, file_path: str) -> List[FunctionNode]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        return _find_functions(source, file_path)
