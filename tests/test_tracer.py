"""End-to-end tests for the call graph tracer."""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracer.graph import CallGraph, FunctionNode
from tracer.parsers.python_parser import PythonParser
from tracer.parsers.javascript_parser import JavaScriptParser
from tracer.parsers.java_parser import JavaParser
from tracer.parsers.c_parser import CParser
from tracer.analyzer import analyze, forward_trace, backward_trace
from tracer.exporters.plantuml_exporter import PlantUMLExporter


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def make_temp(suffix: str, content: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    f.write(textwrap.dedent(content))
    f.close()
    return f.name


# ─────────────────────────────────────────────────────────────────────────────
# Graph unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCallGraph(unittest.TestCase):

    def setUp(self):
        self.graph = CallGraph()
        for name in ("a", "b", "c", "d"):
            self.graph.add_node(FunctionNode(name, name, "f.py", 1, "python"))
        # a -> b -> c -> d
        self.graph.add_edge("a", "b")
        self.graph.add_edge("b", "c")
        self.graph.add_edge("c", "d")

    def test_callees_of(self):
        self.assertEqual(self.graph.callees_of("b"), {"c"})

    def test_callers_of(self):
        self.assertEqual(self.graph.callers_of("c"), {"b"})

    def test_forward_trace(self):
        result = forward_trace(self.graph, "a")
        self.assertEqual(set(result.keys()), {"b", "c", "d"})
        # depth values must be positive integers
        self.assertTrue(all(d >= 1 for d in result.values()))

    def test_backward_trace(self):
        result = backward_trace(self.graph, "d")
        self.assertEqual(set(result.keys()), {"a", "b", "c"})
        self.assertTrue(all(d >= 1 for d in result.values()))

    def test_depth_limit(self):
        result = forward_trace(self.graph, "a", max_depth=1)
        self.assertIn("b", result)
        self.assertNotIn("c", result)
        self.assertNotIn("d", result)

    def test_cycle_safety(self):
        # Add a cycle c -> a
        self.graph.add_edge("c", "a")
        result = forward_trace(self.graph, "a")
        # Should not hang; should contain b, c, d
        self.assertIn("b", result)
        self.assertIn("c", result)


# ─────────────────────────────────────────────────────────────────────────────
# Python parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPythonParser(unittest.TestCase):

    def test_simple_function(self):
        src = """\
            def foo():
                bar()
                baz()

            def bar():
                pass

            def baz():
                bar()
        """
        path = make_temp(".py", src)
        try:
            nodes = PythonParser().parse(path)
            names = {n.name for n in nodes}
            self.assertIn("foo", names)
            self.assertIn("bar", names)
            self.assertIn("baz", names)

            foo = next(n for n in nodes if n.name == "foo")
            self.assertIn("bar", foo.calls)
            self.assertIn("baz", foo.calls)
        finally:
            os.unlink(path)

    def test_class_method(self):
        src = """\
            class MyClass:
                def method_a(self):
                    self.method_b()

                def method_b(self):
                    pass
        """
        path = make_temp(".py", src)
        try:
            nodes = PythonParser().parse(path)
            qnames = {n.qualified_name for n in nodes}
            self.assertIn("MyClass.method_a", qnames)
            self.assertIn("MyClass.method_b", qnames)
        finally:
            os.unlink(path)

    def test_syntax_error_returns_empty(self):
        path = make_temp(".py", "def (broken")
        try:
            nodes = PythonParser().parse(path)
            self.assertEqual(nodes, [])
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# JavaScript parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestJavaScriptParser(unittest.TestCase):

    def test_named_function(self):
        src = """\
            function main() {
              loadData();
              processData();
            }
            function loadData() {}
            function processData() { saveResult(); }
            function saveResult() {}
        """
        path = make_temp(".js", src)
        try:
            nodes = JavaScriptParser().parse(path)
            names = {n.name for n in nodes}
            self.assertIn("main", names)
            self.assertIn("loadData", names)
            self.assertIn("processData", names)
        finally:
            os.unlink(path)

    def test_arrow_function(self):
        src = """\
            const greet = (name) => {
              console.log(name);
            };
        """
        path = make_temp(".js", src)
        try:
            nodes = JavaScriptParser().parse(path)
            names = {n.name for n in nodes}
            self.assertIn("greet", names)
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# Java parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestJavaParser(unittest.TestCase):

    def test_class_methods(self):
        src = """\
            public class OrderService {
                public void createOrder(String id) {
                    validateOrder(id);
                    saveOrder(id);
                }
                private void validateOrder(String id) { }
                private void saveOrder(String id) {
                    notify(id);
                }
                private void notify(String id) { }
            }
        """
        path = make_temp(".java", src)
        try:
            nodes = JavaParser().parse(path)
            names = {n.name for n in nodes}
            self.assertIn("createOrder", names)
            self.assertIn("validateOrder", names)
            self.assertIn("saveOrder", names)
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# C parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCParser(unittest.TestCase):

    def test_c_functions(self):
        src = """\
            int main() {
                read_input();
                process();
                return 0;
            }

            void read_input() { }

            void process() {
                write_output();
            }

            void write_output() { }
        """
        path = make_temp(".c", src)
        try:
            nodes = CParser().parse(path)
            names = {n.name for n in nodes}
            self.assertIn("main", names)
            self.assertIn("read_input", names)
            self.assertIn("process", names)
            self.assertIn("write_output", names)
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# Integration test: full pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration(unittest.TestCase):

    def test_full_python_pipeline(self):
        src = """\
            def entry():
                helper_a()
                helper_b()

            def helper_a():
                common()

            def helper_b():
                common()

            def common():
                pass

            def unrelated():
                pass
        """
        path = make_temp(".py", src)
        try:
            parser = PythonParser()
            nodes = parser.parse(path)

            graph = CallGraph()
            for n in nodes:
                graph.add_node(n)
            graph.resolve_edges()

            results = analyze(graph, "entry")
            self.assertEqual(len(results), 1)
            result = results[0]

            # Forward: entry calls helper_a, helper_b, and transitively common
            self.assertIn("helper_a", result.forward)
            self.assertIn("helper_b", result.forward)
            self.assertIn("common", result.forward)
            self.assertNotIn("unrelated", result.forward)

            # Backward: nothing calls entry
            self.assertEqual(len(result.backward), 0)

            # PlantUML export should succeed
            exporter = PlantUMLExporter()
            diagram = exporter.export(result, graph)
            self.assertIn("@startuml", diagram)
            self.assertIn("@enduml", diagram)
            self.assertIn("entry", diagram)
            self.assertIn("helper_a", diagram)
        finally:
            os.unlink(path)

    def test_backward_trace_integration(self):
        src = """\
            def top():
                mid()

            def mid():
                bottom()

            def bottom():
                pass
        """
        path = make_temp(".py", src)
        try:
            nodes = PythonParser().parse(path)
            graph = CallGraph()
            for n in nodes:
                graph.add_node(n)
            graph.resolve_edges()

            results = analyze(graph, "bottom")
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertIn("mid", result.backward)
            self.assertIn("top", result.backward)
            self.assertEqual(len(result.forward), 0)
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# PlantUML exporter tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPlantUMLExporter(unittest.TestCase):

    def _build_simple_graph(self):
        graph = CallGraph()
        for name, lang in [("entry", "python"), ("helper", "python"), ("low", "python")]:
            graph.add_node(FunctionNode(name, name, "test.py", 1, lang))
        graph.add_edge("entry", "helper")
        graph.add_edge("helper", "low")
        return graph

    def test_export_contains_required_markers(self):
        graph = self._build_simple_graph()
        results = analyze(graph, "helper")
        self.assertEqual(len(results), 1)
        exporter = PlantUMLExporter()
        diagram = exporter.export(results[0], graph)
        self.assertTrue(diagram.startswith("@startuml"))
        self.assertTrue(diagram.strip().endswith("@enduml"))

    def test_export_to_file(self):
        graph = self._build_simple_graph()
        results = analyze(graph, "helper")
        exporter = PlantUMLExporter()
        with tempfile.NamedTemporaryFile(suffix=".puml", delete=False) as f:
            out_path = f.name
        try:
            exporter.export_to_file(results[0], graph, out_path)
            with open(out_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("@startuml", content)
        finally:
            os.unlink(out_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
