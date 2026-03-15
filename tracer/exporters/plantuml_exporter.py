"""Export TraceResult to PlantUML diagram."""

import os
from typing import Dict, Optional

from ..analyzer import TraceResult
from ..graph import CallGraph

# Language color map for node styling
_LANG_COLORS = {
    "python":      "#AED6F1",   # light blue
    "javascript":  "#A9DFBF",   # light green
    "java":        "#F9E79F",   # light yellow
    "c/c++":       "#F1948A",   # light red/pink
    "unknown":     "#D7DBDD",   # light grey
}

_LANG_STEREO = {
    "python":      "<<Python>>",
    "javascript":  "<<JS/TS>>",
    "java":        "<<Java>>",
    "c/c++":       "<<C/C++>>",
}

# Depth-band background colors
_DEPTH_COLORS_BACK = ["#EBF5FB", "#D6EAF8", "#AED6F1", "#85C1E9", "#5DADE2"]
_DEPTH_COLORS_FWRD = ["#EAFAF1", "#D5F5E3", "#A9DFBF", "#7DCEA0", "#52BE80"]


def _sanitize(name: str) -> str:
    """Make a name safe for PlantUML identifiers."""
    return name.replace(".", "_").replace("::", "_").replace("<", "_").replace(">", "_")


def _short_file(path: str) -> str:
    return os.path.basename(path)


def _depth_bg(depth: int, forward: bool) -> str:
    palette = _DEPTH_COLORS_FWRD if forward else _DEPTH_COLORS_BACK
    return palette[min(depth - 1, len(palette) - 1)]


class PlantUMLExporter:
    """
    Generates a PlantUML component diagram from a TraceResult.

    Layout:
      - Left groups  : callers (backward), one package per depth level
      - Centre       : target function (bold blue)
      - Right groups : callees (forward), one package per depth level
      - Arrow labels : [seq] call-order within each caller + depth hop
      - Execution flow note : numbered list of the target's direct callees
    """

    def export(
        self,
        result: TraceResult,
        graph: CallGraph,
        title: Optional[str] = None,
        show_files: bool = True,
        max_label_len: int = 40,
    ) -> str:
        lines = ["@startuml"]
        lines.append("skinparam componentStyle rectangle")
        lines.append("skinparam shadowing false")
        lines.append("skinparam roundcorner 8")
        lines.append("skinparam defaultFontSize 12")
        lines.append("skinparam component {")
        lines.append("  BorderColor #555555")
        lines.append("  FontColor #1A1A1A")
        lines.append("}")
        lines.append("skinparam arrow {")
        lines.append("  Color #555555")
        lines.append("  FontSize 10")
        lines.append("}")
        lines.append("")

        # ── Title ─────────────────────────────────────────────────────────
        depth_info = (
            f"  [max depth: {result.max_depth}]"
            if result.max_depth is not None
            else "  [depth: unlimited]"
        )
        diagram_title = title or f"Call Graph: {result.target.qualified_name}{depth_info}"
        lines.append(f'title "{diagram_title}"')
        lines.append("")

        # ── Legend ────────────────────────────────────────────────────────
        lines.append("legend right")
        lines.append("  **Call Graph Legend**")
        lines.append("  ---")
        lines.append("  Backward (left)  = functions that CALL the target")
        lines.append("  Target  (centre) = traced function")
        lines.append("  Forward (right)  = functions the target CALLS")
        lines.append("  ---")
        lines.append("  Depth groups: hop distance from target")
        lines.append("  Arrow [N] = call sequence within that caller")
        lines.append("  Arrow dN  = depth hop from target")
        lines.append("  ---")
        lines.append("  Language colours:")
        for lang, color in _LANG_COLORS.items():
            if lang != "unknown":
                lines.append(f"  <back:{color}>  </back> {lang}")
        lines.append("endlegend")
        lines.append("")

        # ── Helper: render one node component ─────────────────────────────
        def node_component(qname: str, depth: int = 0, is_target: bool = False) -> str:
            node = graph.nodes.get(qname)
            lang = node.language if node else "unknown"
            color = _LANG_COLORS.get(lang, _LANG_COLORS["unknown"])
            stereo = _LANG_STEREO.get(lang, "")
            safe_id = _sanitize(qname)

            label = qname if len(qname) <= max_label_len else f"...{qname[-(max_label_len-1):]}"
            label_parts = [label]
            if show_files and node:
                label_parts.append(f"[{_short_file(node.file)}:{node.line}]")
            if not is_target and depth > 0:
                label_parts.append(f"depth: {depth}")
            label_str = "\\n".join(label_parts)

            if is_target:
                color = "#2E86C1"
                return f'component "{label_str}" as {safe_id} {stereo} {color} #1A5276 #line.bold'
            return f'component "{label_str}" as {safe_id} {stereo} {color}'

        target_qname = result.target.qualified_name
        target_id = _sanitize(target_qname)

        # ── Execution flow note (direct callees in call order) ─────────────
        ordered_callees = graph.ordered_callees(target_qname)
        # Filter to callees that are in the forward trace or are known nodes
        ordered_callees_in_trace = [
            (c, s) for c, s in ordered_callees
            if c in result.forward or c in graph.nodes
        ]

        if ordered_callees_in_trace:
            lines.append(f'note as ExecFlow')
            lines.append(f'  **Execution Flow of {target_qname}**')
            lines.append(f'  (call order within this function)')
            lines.append(f'  ---')
            for callee_qname, seq in ordered_callees_in_trace:
                node = graph.nodes.get(callee_qname)
                file_info = f"  [{_short_file(node.file)}:{node.line}]" if (show_files and node) else ""
                lines.append(f'  [{seq}] {callee_qname}{file_info}')
            lines.append(f'end note')
            lines.append("")

        # ── Backward groups (one package per depth level) ──────────────────
        if result.backward:
            by_depth: Dict[int, list] = {}
            for qname, d in result.backward.items():
                by_depth.setdefault(d, []).append(qname)

            for d in sorted(by_depth.keys()):
                bg = _depth_bg(d, forward=False)
                label = f"Callers - depth {d}"
                if d == 1:
                    label += "  (direct)"
                lines.append(f'package "{label}" {bg} {{')
                for qname in sorted(by_depth[d]):
                    lines.append(f"  {node_component(qname, depth=d)}")
                lines.append("}")
                lines.append("")

        # ── Target ────────────────────────────────────────────────────────
        lines.append(f"{node_component(target_qname, is_target=True)}")
        lines.append("")

        # ── Forward groups (one package per depth level) ───────────────────
        if result.forward:
            by_depth_fwd: Dict[int, list] = {}
            for qname, d in result.forward.items():
                by_depth_fwd.setdefault(d, []).append(qname)

            for d in sorted(by_depth_fwd.keys()):
                bg = _depth_bg(d, forward=True)
                label = f"Callees - depth {d}"
                if d == 1:
                    label += "  (direct)"
                lines.append(f'package "{label}" {bg} {{')
                for qname in sorted(by_depth_fwd[d]):
                    lines.append(f"  {node_component(qname, depth=d)}")
                lines.append("}")
                lines.append("")

        # ── Edges ─────────────────────────────────────────────────────────
        lines.append("' --- edges ---")

        all_back = set(result.backward)
        all_fwd = set(result.forward)

        def _arrow_label(caller: str, callee: str, depth_val: int) -> str:
            """Build arrow label: [seq] for call order + dN for depth."""
            seq = graph.call_sequence(caller, callee)
            parts = []
            if seq is not None:
                parts.append(f"[{seq}]")
            if depth_val > 0:
                parts.append(f"d{depth_val}")
            return " ".join(parts)

        # Backward edges: callers -> target chain
        for caller, callee in graph.edges:
            caller_in = caller in all_back or caller == target_qname
            callee_in = callee in all_back or callee == target_qname
            if caller_in and callee_in:
                c_id = _sanitize(caller)
                e_id = _sanitize(callee)
                depth_val = result.backward.get(caller, result.backward.get(callee, 0))
                lbl = _arrow_label(caller, callee, depth_val)
                arrow = "-->" if caller != target_qname else "--->"
                label_part = f' : "{lbl}"' if lbl else ""
                lines.append(f"{c_id} {arrow} {e_id}{label_part}")

        # Forward edges: target -> callees chain
        for caller, callee in graph.edges:
            caller_in = caller in all_fwd or caller == target_qname
            callee_in = callee in all_fwd or callee == target_qname
            if caller_in and callee_in:
                c_id = _sanitize(caller)
                e_id = _sanitize(callee)
                depth_val = result.forward.get(callee, result.forward.get(caller, 0))
                lbl = _arrow_label(caller, callee, depth_val)
                label_part = f' : "{lbl}"' if lbl else ""
                lines.append(f"{c_id} --> {e_id}{label_part}")

        lines.append("")
        lines.append("@enduml")
        return "\n".join(lines)

    def export_to_file(
        self,
        result: TraceResult,
        graph: CallGraph,
        output_path: str,
        **kwargs,
    ) -> None:
        content = self.export(result, graph, **kwargs)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"PlantUML diagram written to: {output_path}")
