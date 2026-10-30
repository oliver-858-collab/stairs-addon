"""Dependency-free checks for pure geometry helpers; Blender testing is separate."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'oliver_stairs' / '__init__.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))


def load_function(name):
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace[name]


class TestGeometryHelpers(unittest.TestCase):
    def test_connected_chain(self):
        chains = load_function('_edge_chains')
        self.assertEqual(chains([((1, 2), {}), ((0, 1), {}), ((2, 3), {})]), [[0, 1, 2, 3]])

    def test_closed_chain(self):
        chains = load_function('_edge_chains')
        self.assertEqual(chains([((1, 2), {}), ((0, 1), {}), ((0, 2), {})]), [[0, 1, 2, 0]])

    def test_branch_rejected(self):
        chains = load_function('_edge_chains')
        with self.assertRaises(ValueError):
            chains([((0, 1), {}), ((1, 2), {}), ((1, 3), {})])

    def test_triangle_cut(self):
        cut = load_function('_triangle_section')
        self.assertEqual(cut([(-1, 0, 0), (1, 2, 0), (1, 0, 2)], 0), ((1.0, 0.0), (0.0, 1.0)))
        self.assertIsNone(cut([(1, 0, 0), (1, 2, 0), (1, 0, 2)], 0))


if __name__ == '__main__':
    unittest.main()
