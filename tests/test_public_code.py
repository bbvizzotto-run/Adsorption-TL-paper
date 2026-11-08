"""Fast tests for the data-free public code package."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "endpoints"
sys.path.insert(0, str(BENCH))

import endpoint_tl_benchmark as benchmark
from historical_architecture import AdsorptionAI


class PublicCodeTests(unittest.TestCase):
    def test_benchmark_requires_explicit_data_path(self):
        self.assertIsNone(benchmark.EXPECTED_WORKBOOK_SHA)
        actions = benchmark.build_parser()._subparsers._group_actions[0].choices
        plan_action = next(a for a in actions["plan"]._actions if a.dest == "workbook")
        self.assertTrue(plan_action.required)

    def test_architecture_input_and_output_shapes(self):
        model = AdsorptionAI().build_deep_lstm()
        self.assertEqual(tuple(model.input_shape), (None, 1, 4))
        self.assertEqual(tuple(model.output_shape), (None, 1))
        self.assertEqual([layer.units for layer in model.layers if hasattr(layer, "units")], [128, 64, 32, 16, 1])


if __name__ == "__main__":
    unittest.main()
