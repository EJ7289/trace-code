"""Language parsers for call graph extraction."""

from .base_parser import BaseParser
from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .java_parser import JavaParser
from .c_parser import CParser

EXTENSION_MAP = {
    ".py": PythonParser,
    ".js": JavaScriptParser,
    ".jsx": JavaScriptParser,
    ".ts": JavaScriptParser,
    ".tsx": JavaScriptParser,
    ".java": JavaParser,
    ".c": CParser,
    ".cpp": CParser,
    ".cc": CParser,
    ".cxx": CParser,
    ".h": CParser,
    ".hpp": CParser,
}


def get_parser(file_path: str) -> BaseParser:
    """Return appropriate parser for the given file extension."""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    parser_class = EXTENSION_MAP.get(ext)
    if parser_class is None:
        raise ValueError(f"No parser available for extension '{ext}'")
    return parser_class()
