"""Generate PlantUML activity (logic-flow) diagram from a FunctionBody.

PlantUML v2 activity diagram — valid constructs used here
----------------------------------------------------------
  start / stop
  :action label; #color          coloured action box
  if (entry-condition?) then (yes-label)
    elseif (entry-condition?) then (yes-label)
    else (no-label)
  endif
  while (entry-condition?) is (continue-label)
    ...
  endwhile (exit-label)
  partition "label" #color { ... }   visual container (try/match)
  note right / end note              multiline note attached to previous node

NOT valid in activity diagrams: group / end group  (sequence-diagram-only).

Rendering checklist
-------------------
[x] CallStmt          – blue action box, shows assigned_to if present
[x] AssignStmt        – grey-blue action box  (:target = value;)
[x] ReturnStmt        – green terminal box    (:return value;)
[x] RaiseStmt         – red terminal box      (:raise exc;)
[x] AssertStmt        – diamond: entry=condition, pass branch / fail→raise
[x] BreakStmt         – amber action box      (:break;)  signals loop exit
[x] ContinueStmt      – lavender action box   (:continue;) signals skip
[x] IfBlock           – diamond decision, entry condition shown explicitly
[x] ForBlock          – while loop, entry = "for target in iterable"
[x] WhileBlock        – while loop, entry = condition expression
[x] TryBlock          – partition blocks per clause (try/except.../finally)
[x] SwitchBlock       – partition + if/elseif chain, each case is entry cond
"""

import os
from typing import List, Optional

from ..logic import (
    FunctionBody,
    CallStmt, AssignStmt, ReturnStmt, RaiseStmt,
    AssertStmt, BreakStmt, ContinueStmt,
    IfBlock, ForBlock, WhileBlock, TryBlock,
    SwitchBlock, SwitchCase,
)

# ── Colour palette (Office-style, easy on the eye) ────────────────────────────
_C_CALL    = "#DDEBF7"   # light blue        – function call boxes
_C_ASSIGN  = "#F2F2F2"   # light grey        – assignment boxes
_C_RETURN  = "#E2EFDA"   # light green       – return
_C_RAISE   = "#FCE4D6"   # light red/orange  – raise
_C_BREAK   = "#FFE699"   # amber             – break (loop exit)
_C_CONT    = "#E8DEF8"   # lavender          – continue (skip iteration)
_C_TRY     = "#FFF2CC"   # light yellow      – try block
_C_EXCEPT  = "#FCE4D6"   # light pink/red    – except block
_C_FINALLY = "#E2EFDA"   # light green       – finally block
_C_SWITCH  = "#DAE8FC"   # light cyan-blue   – match/switch container


def _esc(s: str) -> str:
    """Escape characters that break PlantUML activity labels."""
    return (s.replace('"', "'")
             .replace('<', '~<')
             .replace('>', '~>')
             .replace('\n', ' ')
             .replace('{', '(')
             .replace('}', ')'))


class ActivityExporter:
    """Generates a PlantUML v2 activity diagram from a FunctionBody."""

    def export(self, body: FunctionBody, title: Optional[str] = None) -> str:
        lines = ["@startuml"]
        lines += [
            "skinparam backgroundColor #FEFEFE",
            "skinparam activity {",
            f"  BackgroundColor {_C_CALL}",
            "  BorderColor #2874A6",
            "  FontColor #1A1A1A",
            "  FontSize 12",
            "  DiamondBackgroundColor #FFF2CC",
            "  DiamondBorderColor #D6A910",
            "  DiamondFontColor #5D4E00",
            "  ArrowColor #555555",
            "  ArrowFontSize 10",
            "}",
            "",
        ]

        t = title or f"Logic Flow: {body.qualified_name}"
        lines.append(f'title "{_esc(t)}"')
        lines.append("")

        # ── start ────────────────────────────────────────────────────────────
        lines.append("start")
        lines.append("")

        # ── Header note: function signature + source location ────────────────
        file_short = os.path.basename(body.file)
        lines.append("note right")
        lines.append(f"  **{_esc(body.qualified_name)}**")
        if body.params:
            lines.append(f"  //params: {_esc(', '.join(body.params))}//" )
        lines.append(f"  //source: {file_short}:{body.line}//")
        lines.append("end note")
        lines.append("")

        self._render_stmts(body.statements, lines, indent=0)

        lines += ["", "stop", "@enduml"]
        return "\n".join(lines)

    # ── Rendering helpers ────────────────────────────────────────────────────

    def _render_stmts(self, stmts: List, lines: List[str], indent: int) -> None:
        for stmt in stmts:
            self._render_stmt(stmt, lines, indent)

    def _render_stmt(self, stmt, lines: List[str], indent: int) -> None:  # noqa: C901
        pad = "  " * indent

        # ── [x] Function call ───────────────────────────────────────────────
        if isinstance(stmt, CallStmt):
            args = f"({', '.join(stmt.args)})" if stmt.args else "()"
            call_str = f"{stmt.name}{args}"
            if stmt.assigned_to:
                label = _esc(f"{stmt.assigned_to} = {call_str}")
            else:
                label = _esc(call_str)
            lines.append(f"{pad}{_C_CALL}:{label};")

        # ── [x] Non-call assignment ─────────────────────────────────────────
        elif isinstance(stmt, AssignStmt):
            label = _esc(f"{stmt.target} = {stmt.value}")
            lines.append(f"{pad}{_C_ASSIGN}:{label};")

        # ── [x] Return ──────────────────────────────────────────────────────
        elif isinstance(stmt, ReturnStmt):
            val = f" {_esc(stmt.value)}" if stmt.value else ""
            lines.append(f"{pad}{_C_RETURN}:return{val};")

        # ── [x] Raise ───────────────────────────────────────────────────────
        elif isinstance(stmt, RaiseStmt):
            exc = f" {_esc(stmt.exc)}" if stmt.exc else ""
            lines.append(f"{pad}{_C_RAISE}:raise{exc};")

        # ── [x] Assert: entry-condition = assertion condition ────────────────
        #   Renders as: if (assert <cond>?) then (pass) else (fail) → raise
        elif isinstance(stmt, AssertStmt):
            cond = _esc(stmt.condition)
            msg_part = f": {_esc(stmt.msg)}" if stmt.msg else ""
            lines.append(f"{pad}if (assert {cond}?) then (pass)")
            lines.append(f"{pad}else (fail)")
            lines.append(f"{pad}  {_C_RAISE}:raise AssertionError{msg_part};")
            lines.append(f"{pad}endif")

        # ── [x] Break ───────────────────────────────────────────────────────
        elif isinstance(stmt, BreakStmt):
            lines.append(f"{pad}{_C_BREAK}:break  -- exit loop;")

        # ── [x] Continue ────────────────────────────────────────────────────
        elif isinstance(stmt, ContinueStmt):
            lines.append(f"{pad}{_C_CONT}:continue  -- next iteration;")

        # ── [x] if / elif / else ─────────────────────────────────────────────
        #   Entry condition = the boolean expression tested.
        #   yes-branch  = condition is True
        #   no-branch   = condition is False (else / implied else)
        elif isinstance(stmt, IfBlock):
            cond = _esc(stmt.condition)
            lines.append(f"{pad}if ({cond}?) then (yes)")
            self._render_stmts(stmt.then_body, lines, indent + 1)
            for elif_cond, elif_body in stmt.elif_clauses:
                lines.append(f"{pad}elseif ({_esc(elif_cond)}?) then (yes)")
                self._render_stmts(elif_body, lines, indent + 1)
            if stmt.else_body:
                lines.append(f"{pad}else (no)")
                self._render_stmts(stmt.else_body, lines, indent + 1)
            lines.append(f"{pad}endif")

        # ── [x] for loop ─────────────────────────────────────────────────────
        #   Entry condition = "for <target> in <iterable>"
        #   Continue when there is a next element; exit when exhausted.
        elif isinstance(stmt, ForBlock):
            target = _esc(stmt.target)
            iterable = _esc(stmt.iterable)
            lines.append(f"{pad}while (for {target} in {iterable}?) is (next item)")
            self._render_stmts(stmt.body, lines, indent + 1)
            lines.append(f"{pad}endwhile (exhausted)")

        # ── [x] while loop ───────────────────────────────────────────────────
        #   Entry condition = the boolean expression tested each iteration.
        elif isinstance(stmt, WhileBlock):
            cond = _esc(stmt.condition)
            lines.append(f"{pad}while ({cond}?) is (yes)")
            self._render_stmts(stmt.body, lines, indent + 1)
            lines.append(f"{pad}endwhile (no)")

        # ── [x] try / except / finally ───────────────────────────────────────
        #   Each clause rendered as a labelled partition block.
        #   Entry condition for except = the exception type caught.
        elif isinstance(stmt, TryBlock):
            lines.append(f'{pad}partition "try" {_C_TRY} {{')
            self._render_stmts(stmt.body, lines, indent + 1)
            lines.append(f"{pad}}}")
            for exc_type, handler_body in stmt.handlers:
                safe_exc = _esc(exc_type)
                lines.append(f'{pad}partition "except {safe_exc}" {_C_EXCEPT} {{')
                self._render_stmts(handler_body, lines, indent + 1)
                lines.append(f"{pad}}}")
            if stmt.finally_body:
                lines.append(f'{pad}partition "finally" {_C_FINALLY} {{')
                self._render_stmts(stmt.finally_body, lines, indent + 1)
                lines.append(f"{pad}}}")

        # ── [x] match / case (switch) ─────────────────────────────────────────
        #   Container partition labelled "match <subject>".
        #   Entry condition for each case = the pattern being matched.
        elif isinstance(stmt, SwitchBlock):
            subject = _esc(stmt.subject)
            lines.append(f'{pad}partition "match {subject}" {_C_SWITCH} {{')
            non_default = [c for c in stmt.cases if not c.is_default]
            default_cases = [c for c in stmt.cases if c.is_default]

            if non_default:
                first, *rest = non_default
                lines.append(
                    f"{pad}  if (case {_esc(first.pattern)}?) then (match)"
                )
                self._render_stmts(first.body, lines, indent + 2)
                for case in rest:
                    lines.append(
                        f"{pad}  elseif (case {_esc(case.pattern)}?) then (match)"
                    )
                    self._render_stmts(case.body, lines, indent + 2)
                if default_cases:
                    lines.append(f"{pad}  else (default / _)")
                    self._render_stmts(default_cases[0].body, lines, indent + 2)
                lines.append(f"{pad}  endif")
            elif default_cases:
                self._render_stmts(default_cases[0].body, lines, indent + 1)

            lines.append(f"{pad}}}")

    def export_to_file(self, body: FunctionBody, output_path: str, **kwargs) -> None:
        content = self.export(body, **kwargs)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Activity diagram written to: {output_path}")

    # ── Fallback for non-Python (ordered call list only) ─────────────────────

    @staticmethod
    def export_calllist(
        target_qname: str,
        file: str,
        line: int,
        language: str,
        ordered_callees: List,
        output_path: str,
    ) -> None:
        """Simplified activity diagram when full logic parsing is unavailable."""
        lines = [
            "@startuml",
            "skinparam backgroundColor #FEFEFE",
            "skinparam activity {",
            f"  BackgroundColor {_C_CALL}",
            "  BorderColor #2874A6",
            "  FontColor #1A1A1A",
            "  ArrowColor #555555",
            "}",
            "",
            f'title "Logic Flow: {_esc(target_qname)}"',
            "",
            "start",
            "",
            "note right",
            f"  **{_esc(target_qname)}**",
            f"  //source: {os.path.basename(file)}:{line}//",
            f"  //language: {language}//",
            f"  //(detailed control-flow not available for {language})//",
            "end note",
            "",
        ]
        for callee_qname, seq in ordered_callees:
            simple = callee_qname.split(".")[-1] if "." in callee_qname else callee_qname
            lines.append(f"  {_C_CALL}:[{seq}] {_esc(simple)}();")
        lines += ["", "stop", "@enduml"]

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"Activity diagram written to: {output_path}")
