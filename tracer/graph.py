"""Call graph data structures."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FunctionNode:
    """Represents a function/method in the call graph."""
    name: str
    qualified_name: str          # e.g. "ClassName.method_name"
    file: str
    line: int
    language: str
    calls: List[str] = field(default_factory=list)   # unresolved call names, in source order
    # Optional: (callee_name, [arg_str, ...]) pairs in source order.
    # Populated by parsers that support argument extraction (e.g. PythonParser).
    call_sites: List[Tuple[str, List[str]]] = field(default_factory=list)

    def __hash__(self):
        return hash(self.qualified_name)

    def __eq__(self, other):
        return isinstance(other, FunctionNode) and self.qualified_name == other.qualified_name


class CallGraph:
    """Directed call graph: edge A -> B means A calls B."""

    def __init__(self):
        # qualified_name -> FunctionNode
        self.nodes: Dict[str, FunctionNode] = {}
        # (caller_qualified, callee_qualified)
        self.edges: List[Tuple[str, str]] = []
        # caller_qname -> {callee_qname -> sequence_number (1-based, source order)}
        self.call_order: Dict[str, Dict[str, int]] = {}
        # caller_qname -> {callee_qname -> "arg1, arg2, ..."} (from call_sites)
        self.call_args: Dict[str, Dict[str, str]] = {}

    def add_node(self, node: FunctionNode):
        self.nodes[node.qualified_name] = node

    def add_edge(self, caller: str, callee: str):
        edge = (caller, callee)
        if edge not in self.edges:
            self.edges.append(edge)

    def resolve_edges(self):
        """
        Resolve raw call names to qualified names.
        - Adds graph edges for all resolved calls.
        - Records call sequence (source order) in call_order.
        - Records argument strings in call_args (where call_sites is populated).
        """
        name_to_qualified: Dict[str, List[str]] = {}
        for qname, node in self.nodes.items():
            name_to_qualified.setdefault(node.name, []).append(qname)

        for qname, node in self.nodes.items():
            seq_counter = 0
            order_map: Dict[str, int] = {}

            # Build raw_name -> args_str from call_sites (parsers that support it)
            site_args: Dict[str, str] = {}
            for raw_name, raw_args in node.call_sites:
                if raw_name not in site_args:          # first occurrence wins
                    site_args[raw_name] = ", ".join(raw_args)

            for raw_call in node.calls:
                if raw_call in self.nodes:
                    resolved = [raw_call]
                else:
                    resolved = name_to_qualified.get(raw_call, [])

                for callee_qname in resolved:
                    self.add_edge(qname, callee_qname)
                    if callee_qname not in order_map:
                        seq_counter += 1
                        order_map[callee_qname] = seq_counter
                    # Record args if this parser provided them
                    if raw_call in site_args:
                        self.call_args.setdefault(qname, {})[callee_qname] = site_args[raw_call]

            if order_map:
                self.call_order[qname] = order_map

    def call_sequence(self, caller: str, callee: str) -> Optional[int]:
        """Return the call sequence number of callee within caller (1-based), or None."""
        return self.call_order.get(caller, {}).get(callee)

    def ordered_callees(self, caller: str) -> List[Tuple[str, int]]:
        """Return [(callee_qname, seq)] for direct callees of caller, sorted by seq."""
        order_map = self.call_order.get(caller, {})
        callees = [(c, s) for c, s in order_map.items() if c in self.nodes]
        return sorted(callees, key=lambda x: x[1])

    def callers_of(self, qualified_name: str) -> Set[str]:
        """Return direct callers of the given function."""
        return {caller for caller, callee in self.edges if callee == qualified_name}

    def callees_of(self, qualified_name: str) -> Set[str]:
        """Return direct callees of the given function."""
        return {callee for caller, callee in self.edges if caller == qualified_name}

    def find_node(self, name: str) -> Optional[FunctionNode]:
        if name in self.nodes:
            return self.nodes[name]
        matches = [n for n in self.nodes.values() if n.name == name]
        if matches:
            return matches[0]
        return None

    def find_all_nodes(self, name: str) -> List[FunctionNode]:
        """Find all nodes matching a name (simple or qualified)."""
        if name in self.nodes:
            return [self.nodes[name]]
        return [n for n in self.nodes.values() if n.name == name]

    def stats(self) -> Dict:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "languages": list({n.language for n in self.nodes.values()}),
            "files": list({n.file for n in self.nodes.values()}),
        }
