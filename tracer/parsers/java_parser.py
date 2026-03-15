"""Java parser (regex-based)."""

import os
import re
from typing import List

from ..graph import FunctionNode
from .base_parser import BaseParser

_CLASS_PATTERN = re.compile(
    r"\bclass\s+(\w+)"
)

_METHOD_PATTERN = re.compile(
    r"(?:public|private|protected|static|final|abstract|synchronized|native|"
    r"default|override|\s)+"     # modifiers
    r"(?:[\w<>\[\],\s]+?)\s+"    # return type (greedy but lazy on name)
    r"(\w+)\s*\("                # method name
)

_CALL_PATTERN = re.compile(r"\b(\w+)\s*\(")

_SKIP_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "do",
    "synchronized", "new", "return", "throw", "assert",
    "class", "interface", "enum",
})


def _find_methods(source: str, file_path: str) -> List[FunctionNode]:
    lines = source.splitlines()
    nodes: List[FunctionNode] = []
    seen: set = set()

    # Track class at each line (simplified: use last seen class keyword)
    class_at_line: List[str] = [""] * len(lines)
    current_class = ""
    brace_depth = 0
    class_start_depth = -1

    for i, line in enumerate(lines):
        m = _CLASS_PATTERN.search(line)
        if m:
            current_class = m.group(1)
            class_start_depth = brace_depth
        brace_depth += line.count("{") - line.count("}")
        class_at_line[i] = current_class
        if current_class and brace_depth <= class_start_depth:
            current_class = ""
            class_start_depth = -1

    all_matches = []
    for m in _METHOD_PATTERN.finditer(source):
        method_name = m.group(1)
        line_no = source[:m.start()].count("\n")
        pos = (line_no, method_name)
        if pos not in seen:
            seen.add(pos)
            all_matches.append((line_no, method_name, m.start(), m.end()))

    all_matches.sort(key=lambda x: x[0])

    for idx, (line_no, name, start_pos, end_pos) in enumerate(all_matches):
        class_name = class_at_line[line_no] if line_no < len(class_at_line) else ""
        qualified = f"{class_name}.{name}" if class_name else name

        brace_start = source.find("{", end_pos)
        if brace_start == -1:
            body = ""
        else:
            next_start = all_matches[idx + 1][2] if idx + 1 < len(all_matches) else len(source)
            body = source[brace_start:min(next_start, len(source))]

        calls = list({m.group(1) for m in _CALL_PATTERN.finditer(body)
                      if m.group(1) not in _SKIP_KEYWORDS})

        node = FunctionNode(
            name=name,
            qualified_name=qualified,
            file=os.path.abspath(file_path),
            line=line_no + 1,
            language="java",
            calls=calls,
        )
        nodes.append(node)

    return nodes


class JavaParser(BaseParser):
    def parse(self, file_path: str) -> List[FunctionNode]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        return _find_methods(source, file_path)
