import unittest

from .metrics import summarize_runs
from .models import AgentRunResult, Scenario, ScenarioResult


class HarnessMetricsTest(unittest.TestCase):
    def test_summary_separates_route_citation_latency_and_side_effects(self):
        scenario = Scenario("s1", "q", expected_route="knowledge", expected_source_origins=("knowledge",))
        run = AgentRunResult(
            final_answer="answer", latency_ms=20, first_event_latency_ms=3,
            route="knowledge", sources=({"origin": "knowledge"},),
        )
        result = ScenarioResult("s1", True, {}, latency_ms=20, route="knowledge")
        summary = summarize_runs([(scenario, run, result)])
        self.assertEqual(summary["route_accuracy"], 1.0)
        self.assertEqual(summary["source_origin_coverage"], 1.0)
        self.assertIsNone(summary["duplicate_side_effect_rate"])
        self.assertEqual(summary["p95_first_event_latency_ms"], 3)


if __name__ == "__main__":
    unittest.main()
