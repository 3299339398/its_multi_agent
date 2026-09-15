import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from its_multi_agent.backend.app.services.answer_evaluation import evaluate_predictions, evaluate_rules, load_cases, main


class AnswerEvaluationTest(unittest.TestCase):
    def prediction_cli(self, predictions, *options, cases=None):
        cases = cases if cases is not None else [{"id": "a", "expected_route": "direct"}]
        with tempfile.TemporaryDirectory() as directory:
            case_path = Path(directory) / "cases.json"
            prediction_path = Path(directory) / "predictions.json"
            case_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
            prediction_path.write_text(json.dumps(predictions), encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", ["evaluation", "--cases", str(case_path), "--predictions", str(prediction_path), *options]), contextlib.redirect_stdout(output):
                status = main()
            return status, json.loads(output.getvalue())

    def test_cli_fails_missing_wrong_and_blank_predictions(self):
        for rows in ([], [{"id": "a", "route": "knowledge", "answer": "Answer"}],
                     [{"id": "a", "route": "direct", "answer": "  "}]):
            with self.subTest(rows=rows):
                status, report = self.prediction_cli(rows)
                self.assertEqual(status, 1)
                self.assertTrue(report["failures"])

    def test_cli_thresholds_are_explicit_and_configurable(self):
        rows = [{"id": "a", "route": "knowledge", "answer": "Answer"}]
        status, report = self.prediction_cli(rows, "--min-route-accuracy", "0")
        self.assertEqual(status, 0)
        self.assertEqual(report["thresholds"]["route_accuracy"], 0)
        status, _ = self.prediction_cli([], "--min-route-accuracy", "0")
        self.assertEqual(status, 1)

    def test_cli_rejects_invalid_thresholds_and_empty_cases(self):
        for value in ("-1", "1.1", "nan", "inf"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                self.prediction_cli([], "--min-route-accuracy", value)
            self.assertEqual(caught.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.prediction_cli([], cases=[])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_gates_action_and_evidence_metrics(self):
        cases = [{"id": "a", "expected_route": "knowledge", "expected_action": "answer",
                  "relevant_source_ids": ["policy-1"], "answer_terms": [["500"]]}]
        rows = [{"id": "a", "route": "knowledge", "action": "abstain", "answer": "Unsupported"}]
        status, report = self.prediction_cli(rows, cases=cases)
        self.assertEqual(status, 1)
        self.assertEqual({failure["metric"] for failure in report["failures"]},
                         {"action_accuracy", "evidence_recall", "citation_source_precision", "answer_term_coverage"})

    def test_missing_predictions_count_against_coverage_and_accuracy(self):
        cases = [
            {"id": "a", "expected_route": "knowledge", "expected_action": "answer",
             "relevant_source_ids": ["policy-1", "policy-2"], "answer_terms": [["500", "五百"]]},
            {"id": "b", "expected_route": "clarify", "expected_action": "abstain", "relevant_source_ids": []},
        ]
        result = evaluate_predictions(cases, [{
            "id": "a", "route": "knowledge", "action": "answer", "retrieved_source_ids": ["policy-1", "wrong"],
            "answer": "住宿为 500 元。[policy-1] [invented]",
        }])
        self.assertEqual(result["prediction_coverage"], 0.5)
        self.assertEqual(result["route_accuracy"], 0.5)
        self.assertEqual(result["evidence_recall"], 0.5)
        self.assertEqual(result["citation_source_precision"], 0.5)
        self.assertEqual(result["action_accuracy"], 0.5)
        self.assertEqual(result["answer_term_coverage"], 1.0)

    def test_no_citations_is_zero_precision_for_a_grounded_answer(self):
        result = evaluate_predictions([
            {"id": "a", "expected_route": "knowledge", "expected_action": "answer", "relevant_source_ids": ["source-1"]},
        ], [{"id": "a", "route": "knowledge", "action": "answer", "answer": "Unsupported answer"}])
        self.assertEqual(result["citation_source_precision"], 0.0)

    def test_duplicate_and_unknown_prediction_ids_are_rejected(self):
        cases = [{"id": "a", "expected_route": "direct"}]
        for rows in ([{"id": "a"}, {"id": "a"}], [{"id": "unknown"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                evaluate_predictions(cases, rows)

    def test_business_fixtures_enforce_rules_and_semantic_deferrals(self):
        cases = load_cases()
        result = evaluate_rules(cases)
        self.assertGreaterEqual(result["case_count"], 20)
        self.assertEqual(result["failures"], [])
        self.assertGreater(result["semantic_cases"], 0)


if __name__ == "__main__":
    unittest.main()
