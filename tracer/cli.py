"""CLI for the cross-language bidirectional call graph tracer."""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .graph import CallGraph
from .parsers import get_parser, EXTENSION_MAP
from .analyzer import analyze
from .exporters import PlantUMLExporter, ActivityExporter, SequenceExporter


def _collect_source_files(paths: List[str]) -> List[str]:
    """Expand directories recursively; filter to supported extensions."""
    supported_exts = set(EXTENSION_MAP.keys())
    result = []
    for path in paths:
        p = Path(path)
        if p.is_file():
            if p.suffix.lower() in supported_exts:
                result.append(str(p))
            else:
                print(f"  [skip] unsupported extension: {path}", file=sys.stderr)
        elif p.is_dir():
            for ext in supported_exts:
                result.extend(str(f) for f in p.rglob(f"*{ext}"))
        else:
            print(f"  [warn] not found: {path}", file=sys.stderr)
    return sorted(set(result))


def build_graph(source_files: List[str], verbose: bool = False) -> CallGraph:
    graph = CallGraph()
    for fpath in source_files:
        try:
            parser = get_parser(fpath)
            nodes = parser.parse(fpath)
            for node in nodes:
                graph.add_node(node)
            if verbose:
                print(f"  parsed {os.path.basename(fpath)}: {len(nodes)} function(s)")
        except Exception as exc:
            print(f"  [error] {fpath}: {exc}", file=sys.stderr)

    graph.resolve_edges()
    return graph


def _print_tree(
    items: dict,
    direct: set,
    direction: str,
    graph: "CallGraph" = None,
    caller_qname: str = None,
) -> None:
    """Print callers or callees grouped by depth. Shows [N] call order for direct callees."""
    if not items:
        print("    (none)")
        return

    by_depth: dict = {}
    for qname, d in items.items():
        by_depth.setdefault(d, []).append(qname)

    for d in sorted(by_depth.keys()):
        tag = "(direct)" if d == 1 else f"(depth {d})"
        print(f"    {'└─' * d}{tag}")
        for qname in sorted(by_depth[d]):
            marker = "★" if qname in direct else " "
            seq_label = ""
            if direction == "forward" and d == 1 and graph and caller_qname:
                seq = graph.call_sequence(caller_qname, qname)
                if seq is not None:
                    seq_label = f"[{seq}] "
            print(f"    {'  ' * d}  {marker} {seq_label}{qname}")


def _print_execution_flow(target_qname: str, graph: "CallGraph") -> None:
    """Print the numbered execution flow (direct call order) of the target function."""
    ordered = graph.ordered_callees(target_qname)
    if not ordered:
        return
    print(f"  Execution flow (call order within '{target_qname}'):")
    for callee_qname, seq in ordered:
        node = graph.nodes.get(callee_qname)
        file_info = f"  <{os.path.basename(node.file)}:{node.line}>" if node else ""
        args_info = ""
        if graph.call_args.get(target_qname, {}).get(callee_qname):
            args_info = f"  args: ({graph.call_args[target_qname][callee_qname]})"
        print(f"    [{seq}] {callee_qname}{file_info}{args_info}")


def _generate_activity_diagram(
    result, graph: CallGraph, safe_name: str, show_files: bool
) -> None:
    """Generate the internal logic (activity) diagram for the target function."""
    target_node = result.target
    activity_path = f"{safe_name}_activity.puml"

    if target_node.language == "python":
        from .parsers.python_logic_parser import PythonLogicParser
        body = PythonLogicParser().parse_function(
            target_node.file, target_node.qualified_name
        )
        if body:
            ActivityExporter().export_to_file(body, activity_path)
            return

    elif target_node.language == "c/c++":
        from .parsers.c_logic_parser import CLogicParser
        parser = CLogicParser()
        if parser.available():
            body = parser.parse_function(
                target_node.file, target_node.qualified_name
            )
            if body:
                ActivityExporter().export_to_file(body, activity_path)
                return

    # Fallback for unparseable files: show ordered call list
    ordered = graph.ordered_callees(target_node.qualified_name)
    ActivityExporter.export_calllist(
        target_qname=target_node.qualified_name,
        file=target_node.file,
        line=target_node.line,
        language=target_node.language,
        ordered_callees=ordered,
        output_path=activity_path,
    )


def _generate_sequence_diagram(
    result, graph: CallGraph, safe_name: str,
    seq_depth: int, forward_depth: int, show_files: bool
) -> None:
    """Generate the bidirectional sequence diagram for the target function."""
    seq_path = f"{safe_name}_sequence.puml"
    SequenceExporter().export_to_file(
        result, graph, seq_path,
        max_depth=seq_depth,
        forward_depth=forward_depth,
        show_files=show_files,
    )


def run(args: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        prog="tracer",
        description=(
            "╔═══════════════════════════════════════════════════════════════╗\n"
            "║  call-tracer  —  Cross-language call graph tracer             ║\n"
            "╠═══════════════════════════════════════════════════════════════╣\n"
            "║  Given any function, produces THREE PlantUML diagrams:        ║\n"
            "║                                                               ║\n"
            "║  1. Call Graph   (.puml)  — who calls it & what it calls      ║\n"
            "║  2. Activity     (_activity.puml) — internal logic flow       ║\n"
            "║                  if/else, loops, calls, return/raise          ║\n"
            "║  3. Sequence     (_sequence.puml) — caller chain with args    ║\n"
            "║                  who calls it, N levels up, with parameters   ║\n"
            "║                                                               ║\n"
            "║  Supports: Python · JS/TS · Java · C/C++                     ║\n"
            "╚═══════════════════════════════════════════════════════════════╝"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Full analysis with all 3 diagrams:\n"
            "  tracer my_func src/\n\n"
            "  # Limit trace depth and sequence depth:\n"
            "  tracer MyClass.my_method src/ --depth 3 --seq-depth 4\n\n"
            "  # Skip activity/sequence diagrams:\n"
            "  tracer process_request . --no-activity --no-sequence\n\n"
            "  # Trace across mixed-language files:\n"
            "  tracer foo file_a.py file_b.js --verbose\n\n"
            "  # List all functions to find the right name:\n"
            "  tracer placeholder . --list\n\n"
            "Depth guide:\n"
            "  --depth N       how many hops to follow forward/backward\n"
            "  --seq-depth N   how many caller levels to show in sequence diagram\n"
            "                  (default 5, max recommended: 8)\n"
        ),
    )

    parser.add_argument(
        "function",
        help=(
            "Target function to trace. Use simple name ('foo') or "
            "qualified name ('MyClass.foo') to disambiguate."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help=(
            "Source files or directories to scan. "
            "Directories are scanned recursively for all supported file types."
        ),
    )
    parser.add_argument(
        "--depth", "-d",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Max trace depth for call graph (both directions). "
            "Default: unlimited."
        ),
    )
    parser.add_argument(
        "--seq-depth",
        type=int,
        default=5,
        metavar="N",
        help=(
            "Max caller levels (backward) to show in the sequence diagram. "
            "Default: 5."
        ),
    )
    parser.add_argument(
        "--forward-depth",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Max callee levels (forward) to show in the sequence diagram. "
            "Default: 3."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help=(
            "Base path for output files. The call-graph diagram uses this path; "
            "activity and sequence diagrams append '_activity' / '_sequence'. "
            "Default: <function_name>.puml"
        ),
    )
    parser.add_argument(
        "--no-files",
        action="store_true",
        help="Omit file path and line number from all diagram node labels.",
    )
    parser.add_argument(
        "--no-activity",
        action="store_true",
        help="Skip generating the activity (logic-flow) diagram.",
    )
    parser.add_argument(
        "--no-sequence",
        action="store_true",
        help="Skip generating the caller sequence diagram.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print per-file parsing progress during scanning.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help=(
            "List every function discovered in the scanned paths, "
            "then exit. Useful for exploring available function names."
        ),
    )

    opts = parser.parse_args(args)
    show_files = not opts.no_files

    # ── Scan ──────────────────────────────────────────────────────────────
    print(f"Scanning: {', '.join(opts.paths)}")
    source_files = _collect_source_files(opts.paths)
    if not source_files:
        print("No supported source files found.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(source_files)} source file(s).")

    print("Parsing...")
    graph = build_graph(source_files, verbose=opts.verbose)
    stats = graph.stats()
    langs = ", ".join(sorted(stats["languages"])) or "(none)"
    print(
        f"Graph: {stats['nodes']} function(s), {stats['edges']} call edge(s), "
        f"language(s): {langs}"
    )

    # ── List mode ─────────────────────────────────────────────────────────
    if opts.list:
        print("\nDiscovered functions (qualified name -> file:line):")
        for qname, node in sorted(graph.nodes.items()):
            print(f"  {qname:50s}  {os.path.basename(node.file)}:{node.line}")
        return

    # ── Trace ─────────────────────────────────────────────────────────────
    depth_label = f"depth <= {opts.depth}" if opts.depth is not None else "unlimited depth"
    print(f"\nTracing '{opts.function}'  [{depth_label}] ...")
    results = analyze(graph, opts.function, max_depth=opts.depth)

    if not results:
        print(
            f"\n[!] Function '{opts.function}' was not found in the scanned codebase.\n"
            "    Tip: run with --list to see all discovered function names.",
            file=sys.stderr,
        )
        sys.exit(1)

    cg_exporter = PlantUMLExporter()

    for result in results:
        qname = result.target.qualified_name
        back_count = len(result.backward)
        fwd_count = len(result.forward)
        back_depth = result.max_backward_depth()
        fwd_depth = result.max_forward_depth()

        print(f"\n{'=' * 62}")
        print(f"  TARGET  : {qname}")
        print(f"  File    : {result.target.file}:{result.target.line}")
        print(f"  Language: {result.target.language}")
        print(f"  Trace   : {depth_label}")
        print(f"{'-' * 62}")
        print(
            f"  BACKWARD (callers) : {back_count} function(s) "
            f"across {back_depth} depth level(s)"
        )
        print("    * = direct caller   (depth 1)")
        _print_tree(result.backward, result.direct_callers, "backward")
        print(f"{'-' * 62}")
        print(
            f"  FORWARD  (callees) : {fwd_count} function(s) "
            f"across {fwd_depth} depth level(s)"
        )
        print("    * = direct callee   (depth 1)   [N] = call order")
        _print_tree(result.forward, result.direct_callees, "forward",
                    graph=graph, caller_qname=qname)
        print(f"{'-' * 62}")
        _print_execution_flow(qname, graph)

        # ── Determine base output name ─────────────────────────────────────
        safe_name = qname.replace(".", "_").replace("::", "_")
        if opts.output:
            # Strip .puml suffix so we can append _activity, _sequence
            base = opts.output[:-5] if opts.output.lower().endswith(".puml") else opts.output
        else:
            base = safe_name

        # ── Diagram 1: Call graph (.puml) ─────────────────────────────────
        cg_path = f"{base}.puml"
        cg_exporter.export_to_file(result, graph, cg_path, show_files=show_files)

        # ── Diagram 2: Activity / logic-flow (_activity.puml) ─────────────
        if not opts.no_activity:
            _generate_activity_diagram(result, graph, base, show_files)

        # ── Diagram 3: Caller sequence (_sequence.puml) ───────────────────
        if not opts.no_sequence:
            _generate_sequence_diagram(result, graph, base,
                                       opts.seq_depth, opts.forward_depth,
                                       show_files)

    print(f"\n{'=' * 62}")
    print("Done.")
    if not opts.no_activity or not opts.no_sequence:
        print()
        print("  Diagrams generated per function:")
        print("    <name>.puml           Call graph  (callers + callees + depth)")
        print("    <name>_activity.puml  Logic flow  (if/for/while + call order)")
        print("    <name>_sequence.puml  Caller chain (who calls it + args)")
        print()
        print("  Render with: java -jar plantuml.jar *.puml")
        print("  Or paste content at: https://www.plantuml.com/plantuml/uml/")


def main():
    run()


if __name__ == "__main__":
    main()
