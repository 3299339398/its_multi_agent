"""Evaluate routing contracts or observed predictions without provider calls."""

import argparse
import json
import math
import re
from pathlib import Path

from its_multi_agent.backend.app.services.answer_routing import route_by_rules

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "answer_scenarios.json"
PREDICTION_METRICS = ("route_accuracy", "action_accuracy", "evidence_recall",
                      "citation_source_precision", "answer_term_coverage")


def load_cases(path: Path = DEFAULT_CASES) -> list[dict]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation requires a non-empty cases array")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evaluation case IDs")
    return cases


def evaluate_rules(cases: list[dict]) -> dict:
    failures = []
    semantic = 0
    for case in cases:
        plan = route_by_rules(case["question"], has_attachments=case.get("has_attachments", False),
                              previous_question=case.get("previous_question", ""))
        actual = plan.route if plan is not None else "semantic"
        semantic += int(actual == "semantic")
        if actual != case["expected_rule"]:
            failures.append({"id": case["id"], "expected": case["expected_rule"], "actual": actual})
    return {"case_count": len(cases), "passed": len(cases) - len(failures),
            "semantic_cases": semantic, "failures": failures,
            "note": "Synthetic rule contracts only. Semantic planner and answer accuracy are not measured."}


def evaluate_predictions(cases: list[dict], predictions: list[dict]) -> dict:
    if not cases:
        raise ValueError("evaluation requires at least one case")
    if not isinstance(predictions, list):
        raise ValueError("predictions must be a JSON array")
    case_ids = {case["id"] for case in cases}
    observed = {}
    for prediction in predictions:
        key = prediction["id"]
        if key not in case_ids or key in observed:
            raise ValueError(f"unknown or duplicate prediction ID: {key}")
        observed[key] = prediction
    routes, actions, recalls, precisions, term_scores = [], [], [], [], []
    failed_cases = []
    blank_answers = []
    for case in cases:
        row = observed.get(case["id"], {})
        route_correct = row.get("route") == case["expected_route"]
        routes.append(int(route_correct))
        if not route_correct:
            failed_cases.append(case["id"])
        if "expected_action" in case:
            actions.append(int(row.get("action") == case["expected_action"]))
        relevant = set(case.get("relevant_source_ids", []))
        answer = row.get("answer", "")
        if not isinstance(answer, str):
            raise ValueError(f"answer must be text for case: {case['id']}")
        if not answer.strip():
            blank_answers.append(case["id"])
        cited = set(re.findall(r"\[([A-Za-z0-9][\w:-]{0,127})\](?!\()", answer))
        if relevant:
            retrieved = set(row.get("retrieved_source_ids", []))
            recalls.append(len(retrieved & relevant) / len(relevant))
        if relevant or cited:
            precisions.append(len(cited & relevant) / len(cited) if cited else 0.0)
        terms = case.get("answer_terms", [])
        if terms:
            term_scores.append(sum(any(term.casefold() in answer.casefold() for term in alternatives)
                                   for alternatives in terms) / len(terms))

    def mean(values):
        return sum(values) / len(values) if values else None

    return {
        "case_count": len(cases), "prediction_count": len(observed),
        "prediction_coverage": len(observed) / len(cases) if cases else None,
        "route_accuracy": mean(routes), "action_accuracy": mean(actions),
        "evidence_recall": mean(recalls), "citation_source_precision": mean(precisions),
        "answer_term_coverage": mean(term_scores), "route_failures": failed_cases,
        "missing_predictions": sorted(case_ids - observed.keys()), "blank_answers": blank_answers,
        "denominators": {"routes": len(routes), "actions": len(actions), "recall": len(recalls),
                         "citations": len(precisions), "answer_terms": len(term_scores)},
        "note": "Citation IDs and answer terms are proxies; human review is required for semantic correctness.",
    }


def probability(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("threshold must be a finite number between 0 and 1")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--predictions", type=Path, help="Observed JSON predictions, one row per case ID")
    for metric in PREDICTION_METRICS:
        parser.add_argument("--min-" + metric.replace("_", "-"), type=probability, default=1.0,
                            help="Minimum measured " + metric + " (default: 1.0)")
    arguments = parser.parse_args()
    try:
        cases = load_cases(arguments.cases)
        if arguments.predictions:
            report = evaluate_predictions(cases, json.loads(arguments.predictions.read_text(encoding="utf-8")))
            thresholds = {metric: getattr(arguments, "min_" + metric) for metric in PREDICTION_METRICS}
            report["thresholds"] = thresholds
            report["failures"] = [
                {"metric": metric, "actual": report[metric], "minimum": minimum}
                for metric, minimum in thresholds.items()
                if report[metric] is not None and report[metric] < minimum
            ]
            for metric in ("missing_predictions", "blank_answers"):
                if report[metric]:
                    report["failures"].append({"metric": metric, "case_ids": report[metric]})
        else:
            report = evaluate_rules(cases)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report.get("failures")))


if __name__ == "__main__":
    raise SystemExit(main())
