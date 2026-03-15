"""Bidirectional call graph analysis."""

from typing import Dict, List, Optional, Set, Tuple
from .graph import CallGraph, FunctionNode


class TraceResult:
    """Result of a bidirectional trace."""

    def __init__(self, target: FunctionNode, max_depth: Optional[int] = None):
        self.target = target
        self.max_depth = max_depth
        # qualified_name -> depth-from-target (1 = direct)
        self.backward: Dict[str, int] = {}
        # qualified_name -> depth-from-target (1 = direct)
        self.forward: Dict[str, int] = {}
        # Direct callers (depth-1 backward)
        self.direct_callers: Set[str] = set()
        # Direct callees (depth-1 forward)
        self.direct_callees: Set[str] = set()

    def all_nodes(self) -> Set[str]:
        return set(self.backward) | {self.target.qualified_name} | set(self.forward)

    def max_backward_depth(self) -> int:
        return max(self.backward.values(), default=0)

    def max_forward_depth(self) -> int:
        return max(self.forward.values(), default=0)


def backward_trace(
    graph: CallGraph,
    start: str,
    max_depth: Optional[int] = None,
) -> Dict[str, int]:
    """
    BFS backward from `start`: collect all functions that (transitively) call start.
    Returns dict of qualified_name -> depth (1 = direct caller).
    Excludes start itself.
    """
    # depth_map stores the minimum depth each node was reached at
    depth_map: Dict[str, int] = {}
    queue: List[Tuple[str, int]] = [(start, 0)]
    visited: Set[str] = set()

    while queue:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if max_depth is not None and depth >= max_depth:
            continue

        for caller in graph.callers_of(current):
            if caller not in visited:
                caller_depth = depth + 1
                # Record min depth if seen via multiple paths
                if caller not in depth_map or depth_map[caller] > caller_depth:
                    depth_map[caller] = caller_depth
                queue.append((caller, caller_depth))

    depth_map.pop(start, None)
    return depth_map


def forward_trace(
    graph: CallGraph,
    start: str,
    max_depth: Optional[int] = None,
) -> Dict[str, int]:
    """
    BFS forward from `start`: collect all functions that start (transitively) calls.
    Returns dict of qualified_name -> depth (1 = direct callee).
    Excludes start itself.
    """
    depth_map: Dict[str, int] = {}
    queue: List[Tuple[str, int]] = [(start, 0)]
    visited: Set[str] = set()

    while queue:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if max_depth is not None and depth >= max_depth:
            continue

        for callee in graph.callees_of(current):
            if callee not in visited:
                callee_depth = depth + 1
                if callee not in depth_map or depth_map[callee] > callee_depth:
                    depth_map[callee] = callee_depth
                queue.append((callee, callee_depth))

    depth_map.pop(start, None)
    return depth_map


def analyze(
    graph: CallGraph,
    function_name: str,
    max_depth: Optional[int] = None,
) -> List[TraceResult]:
    """
    Run bidirectional trace on `function_name`.
    Returns one TraceResult per matching node (handles ambiguous names).
    """
    nodes = graph.find_all_nodes(function_name)
    if not nodes:
        return []

    results = []
    for node in nodes:
        result = TraceResult(node, max_depth=max_depth)
        qname = node.qualified_name

        result.direct_callers = graph.callers_of(qname)
        result.direct_callees = graph.callees_of(qname)

        result.backward = backward_trace(graph, qname, max_depth)
        result.forward = forward_trace(graph, qname, max_depth)

        results.append(result)

    return results
