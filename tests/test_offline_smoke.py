from __future__ import annotations

import unittest
from decimal import Decimal
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "examples" / "offline_smoke.py"


def load_smoke_module(testcase: unittest.TestCase):
    testcase.assertTrue(SMOKE.is_file(), "examples/offline_smoke.py must exist")
    spec = importlib.util.spec_from_file_location("offline_smoke", SMOKE)
    testcase.assertIsNotNone(spec)
    testcase.assertIsNotNone(spec.loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineSmokeTests(unittest.TestCase):
    def test_fixture_is_linked_from_each_relevant_chapter(self):
        chapters = (
            ROOT / "03_memory" / "3.3_vector_databases.md",
            ROOT / "04_tools" / "4.2_tool_use.md",
            ROOT / "09_agentops" / "9.4_optimization.md",
        )
        for chapter in chapters:
            with self.subTest(chapter=chapter):
                self.assertIn(
                    "../examples/offline_smoke.py",
                    chapter.read_text(encoding="utf-8"),
                )

    def test_vector_search_is_deterministic_and_uses_id_as_tie_breaker(self):
        smoke = load_smoke_module(self)
        documents = (
            {"id": "z-python", "text": "Python file handling", "vector": (1.0, 0.0)},
            {"id": "a-python", "text": "Python context managers", "vector": (1.0, 0.0)},
            {"id": "cooking", "text": "Cooking", "vector": (0.0, 1.0)},
        )
        matches = smoke.offline_vector_search((1.0, 0.0), documents, top_k=2)
        self.assertEqual([match["id"] for match in matches], ["a-python", "z-python"])
        self.assertEqual([match["score"] for match in matches], [1.0, 1.0])

    def test_tool_loop_records_observations_and_requires_finish(self):
        smoke = load_smoke_module(self)
        calls = (
            {"tool": "add", "arguments": {"left": 2, "right": 3}},
            {"tool": "finish", "arguments": {"answer": "5"}},
        )
        result = smoke.run_tool_loop(calls, {"add": lambda left, right: left + right})
        self.assertEqual(result["answer"], "5")
        self.assertEqual(result["observations"], ({"tool": "add", "result": 5},))

        with self.assertRaises(RuntimeError):
            smoke.run_tool_loop((calls[0],), {"add": lambda left, right: left + right})

    def test_cost_sampling_uses_decimal_arithmetic(self):
        smoke = load_smoke_module(self)
        sample = smoke.sample_cost(
            ({"input_tokens": 1000, "output_tokens": 500, "tool_cost_usd": "0.02"},),
            input_usd_per_million=Decimal("2"),
            output_usd_per_million=Decimal("10"),
        )
        self.assertEqual(sample, Decimal("0.027"))


if __name__ == "__main__":
    unittest.main()
