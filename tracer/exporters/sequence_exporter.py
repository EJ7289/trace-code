"""Generate PlantUML sequence diagram — bidirectional: callers + callees.

Layout
------
  [deepest caller] → ... → [direct caller] → [TARGET] → [callee] → [sub-callee]
                                                       ← return ←  ← return ←
  ← return ←       ← return ←

The diagram renders in execution order:
  1. Caller chain calls down to TARGET (left → right, dashed for no-depth)
  2. TARGET calls each callee in source order (left → right)
     - Each callee recursively calls its own callees (bounded by forward_depth)
     - Return arrows flow right → left after each sub-tree
  3. TARGET returns back up through the caller chain (right → left)

Arrows
------
  →   solid:   function call     label = [seq] callee_name(args)
  --> dashed:  return            label = return
"""

import os
from typing import Dict, List, Optional, Set, Tuple

from ..analyzer import TraceResult
from ..graph import CallGraph


# ── Helpers ───────────────────────────────────────────────────────────────────

def _san(name: str) -> str:
    """Sanitise a qualified name to a valid PlantUML participant alias."""
    return (name.replace(".", "_").replace("::", "_")
                .replace("<", "_").replace(">", "_")
                .replace("-", "_").replace(" ", "_"))


def _simple(qname: str) -> str:
    """Last component of a qualified / scoped name."""
    for sep in ("::", "."):
        if sep in qname:
            return qname.split(sep)[-1]
    return qname


def _short_file(path: str) -> str:
    return os.path.basename(path)


def _truncate(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


# ── Participant collector ──────────────────────────────────────────────────────

def _collect_forward(
    caller: str,
    graph: CallGraph,
    depth: int,
    max_depth: int,
    seen: Set[str],
    out: List[str],
) -> None:
    """DFS: collect all callee qnames reachable within max_depth, in order."""
    if depth > max_depth:
        return
    for callee, _seq in graph.ordered_callees(caller):
        if callee not in graph.nodes:
            continue
        if callee not in seen:
            seen.add(callee)
            out.append(callee)
        _collect_forward(callee, graph, depth + 1, max_depth, seen, out)


# ── Forward call-tree renderer ────────────────────────────────────────────────

def _render_forward(
    caller: str,
    graph: CallGraph,
    depth: int,
    max_depth: int,
    visited: Set[str],
    lines: List[str],
) -> None:
    """Recursively emit call + return arrows for the forward call tree."""
    if depth > max_depth:
        return

    for callee, seq in graph.ordered_callees(caller):
        if callee not in graph.nodes:
            continue

        args_str = graph.call_args.get(caller, {}).get(callee, "")
        callee_label = _simple(callee)
        if args_str:
            call_label = _truncate(f"[{seq}] {callee_label}({args_str})")
        else:
            call_label = f"[{seq}] {callee_label}()"

        lines.append(f"{_san(caller)} -> {_san(callee)} : {call_label}")

        # Recurse into callee (guard against infinite loops via visited set)
        if callee not in visited:
            visited.add(callee)
            _render_forward(callee, graph, depth + 1, max_depth, visited, lines)
            visited.discard(callee)

        lines.append(f"{_san(callee)} --> {_san(caller)} : return")


# ── Backward chain builder ────────────────────────────────────────────────────

def _build_caller_chain(
    target: str,
    backward: Dict[str, int],
    graph: CallGraph,
    max_depth: int,
) -> List[Tuple[str, str]]:
    """
    Return [(caller, callee), ...] representing the call path from the
    deepest caller down to target, sorted outermost → innermost.

    Strategy: build a reverse-BFS tree from target upward, then extract
    the longest chain (preferring highest-depth nodes at each step).
    """
    # Build adjacency: callee → callers (restricted to backward set)
    backward_set = set(backward)
    parent: Dict[str, Optional[str]] = {target: None}

    # BFS outward through callers
    frontier = [target]
    while frontier:
        next_frontier = []
        for node in frontier:
            callers = [
                c for c in graph.callers_of(node)
                if c in backward_set and c not in parent
            ]
            for c in callers:
                parent[c] = node
                next_frontier.append(c)
        frontier = next_frontier

    # Find deepest node
    if not backward:
        return []
    deepest = max(backward.items(), key=lambda x: x[1])[0]

    # Walk from deepest back to target
    chain: List[str] = []
    cur: Optional[str] = deepest
    while cur is not None and cur != target:
        chain.append(cur)
        cur = parent.get(cur)
    chain.reverse()

    # Convert to (caller, callee) pairs going toward target
    pairs: List[Tuple[str, str]] = []
    path = chain + [target]
    for i in range(len(path) - 1):
        pairs.append((path[i], path[i + 1]))
    return pairs


# ── Main exporter ─────────────────────────────────────────────────────────────

class SequenceExporter:
    """
    Bidirectional PlantUML sequence diagram.

    Shows:
      - Caller chain  (backward, up to backward_depth levels above target)
      - Target function
      - Callee tree   (forward, up to forward_depth levels below target)

    All call arrows carry [seq] label + argument values (where available).
    All return arrows are dashed (-->).
    """

    def export(
        self,
        result: TraceResult,
        graph: CallGraph,
        title: Optional[str] = None,
        max_depth: int = 5,        # backward (caller) depth
        forward_depth: int = 3,    # forward (callee) depth
        show_files: bool = True,
    ) -> str:
        target_qname = result.target.qualified_name
        target_node  = result.target

        backward = {k: v for k, v in result.backward.items() if v <= max_depth}

        lines = ["@startuml"]
        lines += [
            "skinparam sequenceArrowThickness 2",
            "skinparam roundcorner 5",
            "skinparam maxMessageSize 220",
            "skinparam sequence {",
            "  ParticipantBackgroundColor #EBF5FB",
            "  ParticipantBorderColor #2874A6",
            "  ParticipantFontColor #1A1A1A",
            "  ArrowColor #555555",
            "  ArrowFontColor #333333",
            "  ArrowFontSize 11",
            "  LifeLineBackgroundColor #FEFEFE",
            "}",
            "",
        ]

        t = title or f"Sequence Flow: {target_qname}"
        lines.append(f'title "{t}"')
        lines.append("")

        # ── Legend ────────────────────────────────────────────────────────────
        lines.append("legend right")
        lines.append("  **Sequence Flow Legend**")
        lines.append("  ---")
        lines.append("  →   call   : [N] func_name(args)")
        lines.append("  --> return : return")
        lines.append(f"  Callers shown : up to {max_depth} levels above target")
        lines.append(f"  Callees shown : up to {forward_depth} levels below target")
        lines.append("endlegend")
        lines.append("")

        # ── Caller chain ──────────────────────────────────────────────────────
        caller_chain = _build_caller_chain(target_qname, backward, graph, max_depth)

        # ── Forward callee list ───────────────────────────────────────────────
        forward_seen: Set[str] = {target_qname}
        forward_nodes: List[str] = []
        _collect_forward(target_qname, graph, 1, forward_depth,
                         forward_seen, forward_nodes)

        # ── Participants ──────────────────────────────────────────────────────
        # Left side: callers (deepest first)
        caller_participants = []
        seen_participants: Set[str] = set()
        for caller, _ in caller_chain:
            if caller not in seen_participants:
                seen_participants.add(caller)
                caller_participants.append(caller)

        for qname in caller_participants:
            node = graph.nodes.get(qname)
            safe = _san(qname)
            label = _simple(qname)
            depth = backward.get(qname, 0)
            if show_files and node:
                label += f"\\n[{_short_file(node.file)}:{node.line}]"
            label += f"\\n(caller d{depth})"
            lines.append(f'participant "{label}" as {safe}')

        # Centre: target (highlighted)
        target_safe  = _san(target_qname)
        target_label = _simple(target_qname)
        if show_files:
            target_label += f"\\n[{_short_file(target_node.file)}:{target_node.line}]"
        target_label += "\\n** TARGET **"
        lines.append(f'participant "{target_label}" as {target_safe} #2E86C1')

        # Right side: callees
        for qname in forward_nodes:
            node = graph.nodes.get(qname)
            safe  = _san(qname)
            label = _simple(qname)
            if show_files and node:
                label += f"\\n[{_short_file(node.file)}:{node.line}]"
            lines.append(f'participant "{label}" as {safe}')

        lines.append("")

        # ── Phase 1: caller chain calls down to target ────────────────────────
        for caller, callee in caller_chain:
            args_str = graph.call_args.get(caller, {}).get(callee, "")
            callee_label = _simple(callee)
            if args_str:
                call_label = _truncate(f"{callee_label}({args_str})")
            else:
                call_label = f"{callee_label}()"
            lines.append(f"{_san(caller)} -> {_san(callee)} : {call_label}")

        if caller_chain:
            lines.append("")

        # ── Phase 2: target calls its callee tree ─────────────────────────────
        _render_forward(target_qname, graph, 1, forward_depth,
                        {target_qname}, lines)

        if caller_chain:
            lines.append("")

        # ── Phase 3: return back through caller chain ─────────────────────────
        for caller, callee in reversed(caller_chain):
            lines.append(f"{_san(callee)} --> {_san(caller)} : return")

        lines += ["", "@enduml"]
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
        print(f"Sequence diagram written to: {output_path}")
