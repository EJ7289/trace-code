"""Generate PlantUML sequence diagram showing a function's internal logic flow.

Unlike sequence_exporter.py (which shows the caller chain), this exporter
renders the **internal control flow** of a single function as a sequence
diagram, with:

  - Each called function as a separate participant (with activate/deactivate)
  - Control flow mapped to PlantUML constructs:
      if/else   → alt / else / end
      for/while → loop / end
      switch    → alt (case1) / else (case2) / ... / end
  - Variable assignments as self-messages
  - Return statements as dashed arrows back to Caller
  - Comments from source code used as descriptions

The output style matches the hand-crafted test_dirty_code_sequence.puml example.
"""

import os
import re
from typing import Dict, List, Optional, Set

from ..logic import (
    FunctionBody, CallStmt, AssignStmt, ReturnStmt,
    BreakStmt, ContinueStmt, GotoStmt, LabelStmt,
    IfBlock, ForBlock, WhileBlock, SwitchBlock, SwitchCase,
)


def _esc(s: str) -> str:
    """Escape characters that may break PlantUML labels."""
    # Note: < and > are fine in PlantUML sequence diagram message text
    return s.replace('"', "'")


def _short(s: str, n: int = 80) -> str:
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n - 3] + '...'


def _make_alias(name: str) -> str:
    """Generate a valid PlantUML participant alias from a function name."""
    return name.replace('::', '_').replace('.', '_')


class LogicSequenceExporter:
    """Generates a PlantUML sequence diagram from a FunctionBody.

    Args:
        body:           The parsed function logic
        defined_funcs:  Set of function names defined in the same source file.
                        Called functions in this set become separate participants;
                        others (e.g. printf) are shown as self-messages.
        func_summaries: Optional dict of {func_name: short_description} for
                        annotating return arrows. If not provided, uses generic text.
    """

    def __init__(self):
        self._lines: List[str] = []
        self._indent = 0
        self._main_alias = 'Main'
        self._participants: Dict[str, str] = {}  # name -> alias
        self._defined_funcs: Set[str] = set()
        self._func_summaries: Dict[str, str] = {}

    def export(
        self,
        body: FunctionBody,
        defined_funcs: Set[str],
        func_summaries: Optional[Dict[str, str]] = None,
        title: Optional[str] = None,
    ) -> str:
        self._lines = []
        self._indent = 0
        self._defined_funcs = defined_funcs - {body.qualified_name}
        self._func_summaries = func_summaries or {}
        self._participants = {}

        # Phase 1: discover all called functions that should be participants
        self._discover_participants(body.statements)

        # Phase 2: generate the diagram
        self._gen_header(body, title)
        self._gen_body(body)
        self._gen_footer(body)

        return '\n'.join(self._lines)

    def export_to_file(self, body: FunctionBody, output_path: str, **kwargs) -> None:
        content = self.export(body, **kwargs)
        with open(output_path, 'w', encoding='utf-8') as fh:
            fh.write(content)
        print(f"Logic-sequence diagram written to: {output_path}")

    # ── Phase 1: Discover participants ────────────────────────────────────────

    def _discover_participants(self, stmts: List) -> None:
        """Walk the AST to find all function calls to file-defined functions."""
        for stmt in stmts:
            self._discover_in_stmt(stmt)

    def _discover_in_stmt(self, stmt) -> None:
        if isinstance(stmt, CallStmt):
            if stmt.name in self._defined_funcs and stmt.name not in self._participants:
                self._participants[stmt.name] = _make_alias(stmt.name)

        elif isinstance(stmt, IfBlock):
            # Check if-condition for function calls to defined functions
            self._discover_calls_in_text(stmt.condition)
            self._discover_participants(stmt.then_body)
            for elif_cond, elif_body in stmt.elif_clauses:
                self._discover_calls_in_text(elif_cond)
                self._discover_participants(elif_body)
            self._discover_participants(stmt.else_body)

        elif isinstance(stmt, (WhileBlock, ForBlock)):
            self._discover_participants(stmt.body)

        elif isinstance(stmt, SwitchBlock):
            for case in stmt.cases:
                self._discover_participants(case.body)

    def _discover_calls_in_text(self, text: str) -> None:
        """Find function calls to defined functions within condition text."""
        for m in re.finditer(r'(\w+)\s*\(', text):
            name = m.group(1)
            if name in self._defined_funcs and name not in self._participants:
                self._participants[name] = _make_alias(name)

    # ── Phase 2: Generate header ──────────────────────────────────────────────

    def _gen_header(self, body: FunctionBody, title: Optional[str]) -> None:
        safe = body.qualified_name.replace('.', '_').replace('::', '_')
        self._lines.append(f'@startuml {safe}_sequence')

        t = title or f'{body.qualified_name} 循序圖 (Sequence Diagram)'
        self._lines.append(f'title {t}')
        self._lines.append('skinparam sequenceMessageAlign center')
        self._lines.append('skinparam maxMessageSize 200')
        self._lines.append('')

        # Participants
        self._lines.append('actor "呼叫者" as Caller')
        self._lines.append(f'participant "{body.qualified_name}" as {self._main_alias}')
        for name in self._participants:
            alias = self._participants[name]
            self._lines.append(f'participant "{name}" as {alias}')
        self._lines.append('')

    # ── Phase 2: Generate body ────────────────────────────────────────────────

    def _gen_body(self, body: FunctionBody) -> None:
        # Opening: caller invokes the function
        params_str = ', '.join(body.params)
        self._emit(f'== 呼叫主函式 ==')
        self._emit('')
        self._emit(f'Caller -> {self._main_alias} : {body.qualified_name}({params_str})')
        self._emit(f'activate {self._main_alias}')
        self._emit('')

        # Group leading variable declarations
        stmts = list(body.statements)
        leading_decls, remaining = self._split_leading_decls(stmts)
        if leading_decls:
            parts = []
            for d in leading_decls:
                parts.append(f'{d.target}={d.value}')
            self._emit(f'{self._main_alias} -> {self._main_alias} : 初始化 {", ".join(parts)}')
            self._emit('')

        # Process remaining statements
        self._process_stmts(remaining)

    def _gen_footer(self, body: FunctionBody) -> None:
        self._emit('')
        self._emit(f'deactivate {self._main_alias}')
        self._emit('')
        self._emit('@enduml')

    # ── Statement processing ──────────────────────────────────────────────────

    def _process_stmts(self, stmts: List) -> None:
        for stmt in stmts:
            self._process_stmt(stmt)

    def _process_stmt(self, stmt) -> None:  # noqa: C901
        if isinstance(stmt, CallStmt):
            self._process_call(stmt)

        elif isinstance(stmt, AssignStmt):
            self._process_assign(stmt)

        elif isinstance(stmt, ReturnStmt):
            self._process_return(stmt)

        elif isinstance(stmt, BreakStmt):
            self._emit(f'{self._main_alias} -> {self._main_alias} : break')

        elif isinstance(stmt, ContinueStmt):
            self._emit(f'{self._main_alias} -> {self._main_alias} : continue')

        elif isinstance(stmt, GotoStmt):
            self._emit(f'{self._main_alias} -> {self._main_alias} : goto {stmt.label}')

        elif isinstance(stmt, LabelStmt):
            self._emit(f'note over {self._main_alias} : {stmt.name}:')

        elif isinstance(stmt, IfBlock):
            self._process_if(stmt)

        elif isinstance(stmt, (WhileBlock, ForBlock)):
            self._process_loop(stmt)

        elif isinstance(stmt, SwitchBlock):
            self._process_switch(stmt)

    # ── Function calls ────────────────────────────────────────────────────────

    def _process_call(self, stmt: CallStmt) -> None:
        args_str = ', '.join(stmt.args)
        call_text = f'{stmt.name}({args_str})'

        if stmt.assigned_to:
            call_text = f'{stmt.assigned_to} = {call_text}'

        if stmt.name in self._participants:
            alias = self._participants[stmt.name]
            self._emit(f'{self._main_alias} -> {alias} : {call_text}')
            self._emit(f'activate {alias}')

            # Return arrow with summary
            summary = self._func_summaries.get(stmt.name, 'return')
            self._emit(f'{alias} --> {self._main_alias} : {summary}')
            self._emit(f'deactivate {alias}')
        else:
            # External/unknown function → self-message
            self._emit(f'{self._main_alias} -> {self._main_alias} : {call_text}')

    # ── Assignments ───────────────────────────────────────────────────────────

    def _process_assign(self, stmt: AssignStmt) -> None:
        if stmt.value:
            text = f'{stmt.target} = {stmt.value}'
        else:
            text = stmt.target
        self._emit(f'{self._main_alias} -> {self._main_alias} : {_short(text)}')

    # ── Return ────────────────────────────────────────────────────────────────

    def _process_return(self, stmt: ReturnStmt) -> None:
        val = stmt.value if stmt.value else ''
        self._emit(f'{self._main_alias} --> Caller : return {val}'.rstrip())

    # ── If/else ───────────────────────────────────────────────────────────────

    def _process_if(self, stmt: IfBlock) -> None:
        # Check if the condition is a function call to a known participant
        cond_call = self._extract_condition_call(stmt.condition)
        if cond_call:
            func_name, args_str = cond_call
            self._process_condition_call(func_name, args_str)
            # Simplify the alt label
            alt_label = f'{func_name}() == true'
        else:
            alt_label = _esc(stmt.condition)

        self._emit(f'alt {alt_label}')
        self._indent += 1
        self._process_stmts(stmt.then_body)
        self._indent -= 1

        for elif_cond, elif_body in stmt.elif_clauses:
            self._emit(f'else {_esc(elif_cond)}')
            self._indent += 1
            self._process_stmts(elif_body)
            self._indent -= 1

        if stmt.else_body:
            self._emit(f'else')
            self._indent += 1
            self._process_stmts(stmt.else_body)
            self._indent -= 1

        self._emit('end')

    def _extract_condition_call(self, cond: str) -> Optional[tuple]:
        """Check if a condition is a function call to a known participant.
        Returns (func_name, args_str) or None."""
        m = re.match(r'^(\w+)\s*\((.+)\)$', cond.strip())
        if m:
            func_name = m.group(1)
            if func_name in self._participants:
                return func_name, m.group(2)
        return None

    def _process_condition_call(self, func_name: str, args_str: str) -> None:
        """Emit a function call extracted from a condition (before the alt)."""
        alias = self._participants[func_name]
        self._emit(f'{self._main_alias} -> {alias} : {func_name}({args_str})')
        self._emit(f'activate {alias}')
        summary = self._func_summaries.get(func_name, 'true / false')
        self._emit(f'{alias} --> {self._main_alias} : {summary}')
        self._emit(f'deactivate {alias}')

    # ── Loops ─────────────────────────────────────────────────────────────────

    def _process_loop(self, stmt) -> None:
        if isinstance(stmt, ForBlock):
            desc = f'for {stmt.target} in {stmt.iterable}'
        else:
            desc = stmt.condition
        self._emit(f'loop {_esc(desc)}')
        self._indent += 1
        self._process_stmts(stmt.body)
        self._indent -= 1
        self._emit('end')

    # ── Switch/case ───────────────────────────────────────────────────────────

    def _process_switch(self, stmt: SwitchBlock) -> None:
        cases = stmt.cases
        if not cases:
            return

        first = cases[0]
        label = 'default' if first.is_default else f'{stmt.subject} == {first.pattern}'
        self._emit(f'alt {_esc(label)}')
        self._indent += 1
        self._process_stmts(self._strip_break(first.body))
        self._indent -= 1

        for case in cases[1:]:
            label = 'default' if case.is_default else f'{stmt.subject} == {case.pattern}'
            self._emit(f'else {_esc(label)}')
            self._indent += 1
            self._process_stmts(self._strip_break(case.body))
            self._indent -= 1

        self._emit('end')

    def _strip_break(self, stmts: List) -> List:
        """Remove trailing BreakStmt from case body (implicit in alt/else)."""
        if stmts and isinstance(stmts[-1], BreakStmt):
            return stmts[:-1]
        return stmts

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _split_leading_decls(self, stmts: List):
        """Split leading AssignStmt (variable initializations) from rest."""
        decls: List[AssignStmt] = []
        i = 0
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, AssignStmt):
                decls.append(stmt)
            else:
                break
        else:
            i = len(stmts)
        if decls:
            return decls, stmts[len(decls):]
        return [], stmts

    def _emit(self, line: str) -> None:
        pad = '    ' * self._indent
        self._lines.append(f'{pad}{line}')


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: generate function summaries from simple function bodies
# ═══════════════════════════════════════════════════════════════════════════════

def build_func_summaries(
    func_bodies: Dict[str, FunctionBody],
) -> Dict[str, str]:
    """Analyse simple helper functions and produce one-line descriptions.

    Used as the return-arrow label when the function is called in the
    sequence diagram.
    """
    summaries: Dict[str, str] = {}

    for name, body in func_bodies.items():
        stmts = body.statements
        if not stmts:
            summaries[name] = 'return'
            continue

        # Single-statement bodies
        if len(stmts) == 1:
            s = stmts[0]
            if isinstance(s, CallStmt) and s.name == 'printf':
                # printf → describe what's printed
                if s.args:
                    fmt = s.args[0].strip('"').replace('\\n', '')
                    summaries[name] = f'印出 "{_short(fmt, 40)}"'
                else:
                    summaries[name] = 'printf()'
                continue

            if isinstance(s, ReturnStmt):
                summaries[name] = s.value if s.value else 'return'
                continue

            if isinstance(s, AssignStmt):
                if s.value:
                    summaries[name] = f'{s.target} = {s.value}'
                else:
                    summaries[name] = s.target
                continue

        summaries.setdefault(name, 'return')

    return summaries
