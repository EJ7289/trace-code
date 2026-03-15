"""Data structures representing a function's internal logic flow.

Feature checklist
-----------------
[x] CallStmt          – function call (with optional assignment target)
[x] AssignStmt        – variable assignment / augmented assignment
[x] ReturnStmt        – return statement
[x] RaiseStmt         – raise / throw statement
[x] AssertStmt        – assert (condition + optional message)
[x] BreakStmt         – break out of loop
[x] ContinueStmt      – continue to next loop iteration
[x] IfBlock           – if / elif / else with entry condition
[x] ForBlock          – for loop with target + iterable as entry condition
[x] WhileBlock        – while loop with entry condition
[x] TryBlock          – try / except (multiple handlers) / finally
[x] SwitchBlock       – match/case (Python 3.10+) as switch/case
[x] FunctionBody      – top-level container (params, source info, statements)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CallStmt:
    """A function call, optionally with an assignment target.
    e.g.  foo(x, y)          → name='foo', args=['x','y'], assigned_to=''
          result = foo(x)    → name='foo', args=['x'],     assigned_to='result'
    """
    name: str
    args: List[str] = field(default_factory=list)
    assigned_to: str = ""        # variable receiving the return value, or ""


@dataclass
class AssignStmt:
    """A variable assignment whose RHS is NOT a plain function call.
    e.g.  x = 5    /    x += 1    /    items = [1, 2, 3]
    """
    target: str
    value: str


@dataclass
class ReturnStmt:
    """A return statement."""
    value: str = ""


@dataclass
class RaiseStmt:
    """A raise/throw statement."""
    exc: str = ""


@dataclass
class AssertStmt:
    """An assert statement.
    Rendered as: if (condition?) then (ok) else (fail → AssertionError) endif
    """
    condition: str
    msg: str = ""


@dataclass
class BreakStmt:
    """A break statement (exit current loop)."""


@dataclass
class ContinueStmt:
    """A continue statement (skip to next loop iteration)."""


@dataclass
class IfBlock:
    """An if / elif / else block."""
    condition: str
    then_body: List = field(default_factory=list)
    elif_clauses: List[Tuple[str, List]] = field(default_factory=list)
    else_body: List = field(default_factory=list)


@dataclass
class ForBlock:
    """A for loop.  Entry condition = 'for target in iterable'."""
    target: str
    iterable: str
    body: List = field(default_factory=list)


@dataclass
class WhileBlock:
    """A while loop.  Entry condition = condition expression."""
    condition: str
    body: List = field(default_factory=list)


@dataclass
class TryBlock:
    """A try / except / finally block."""
    body: List = field(default_factory=list)
    handlers: List[Tuple[str, List]] = field(default_factory=list)
    finally_body: List = field(default_factory=list)


@dataclass
class SwitchCase:
    """One arm of a match/switch block."""
    pattern: str
    body: List = field(default_factory=list)
    is_default: bool = False


@dataclass
class SwitchBlock:
    """A match/switch statement (Python 3.10+ match/case)."""
    subject: str
    cases: List[SwitchCase] = field(default_factory=list)


@dataclass
class FunctionBody:
    """The parsed internal logic structure of a function."""
    qualified_name: str
    file: str
    line: int
    language: str
    params: List[str] = field(default_factory=list)
    statements: List = field(default_factory=list)
