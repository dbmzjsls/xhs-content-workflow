"""Fixture-driven Brief evaluation with a safe deterministic default.

The default ``mock-hard`` mode constructs the mock provider directly. It does
not consult application settings, API keys, or an ambient ``.env`` file.
``real-soft`` is intentionally manual and requires an explicit paid-provider
opt-in on every invocation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import yaml

from app.config import ROOT_DIR
from app.services import content_pipeline

DEFAULT_CASES_PATH = ROOT_DIR / "evals" / "brief_cases.yaml"
REQUIRED_BRIEF_FIELDS = (
    "topic",
    "audience",
    "product_function",
    "pain_point",
    "style_preference",
)


def load_brief_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    """Load and strictly validate the fixed Brief regression cases."""
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("Brief eval file must contain a non-empty cases list")

    validated: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for item in cases:
        if not isinstance(item, dict) or set(item) != {"id", "brief"}:
            raise ValueError("every Brief eval case must contain only id and brief")
        identifier = item["id"]
        brief = item["brief"]
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Brief eval case id must be a non-empty string")
        if identifier in identifiers:
            raise ValueError(f"duplicate Brief eval case id: {identifier}")
        if not isinstance(brief, dict) or set(brief) != set(REQUIRED_BRIEF_FIELDS):
            raise ValueError("Brief eval case has an invalid field set")
        if not all(isinstance(brief[field], str) and brief[field] for field in REQUIRED_BRIEF_FIELDS):
            raise ValueError("Brief eval fields must be non-empty strings")
        identifiers.add(identifier)
        validated.append({"id": identifier, "brief": dict(brief)})
    return validated


def _result_summary(identifier: str, result: dict[str, Any]) -> dict[str, Any]:
    failures = [
        {
            "candidate": candidate["candidate"],
            "issues": candidate["hard_report"]["issues"],
        }
        for candidate in result["candidates"]
        if candidate["hard_report"]["passed"] is not True
    ]
    return {
        "id": identifier,
        "provider": result["provider"],
        "model": result["model"],
        "candidate_count": len(result["candidates"]),
        "recommended_candidate": result["recommended_candidate"],
        "passed": not failures and result["recommended_candidate"] is not None,
        "failures": failures,
        "soft_scores": {
            str(candidate["candidate"]): candidate["score_report"]
            for candidate in result["candidates"]
        },
    }


def evaluate_mock_hard(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    """Run deterministic hard-rule regression cases without provider lookup."""
    provider = content_pipeline.MockPipelineProvider()
    return [
        _result_summary(
            case["id"],
            content_pipeline.generate_candidate_round(case["brief"], provider=provider),
        )
        for case in load_brief_cases(path)
    ]


def evaluate_real_soft(
    path: Path = DEFAULT_CASES_PATH,
    *,
    allow_paid_providers: bool = False,
) -> list[dict[str, Any]]:
    """Run manual real-model cases after an explicit paid-provider opt-in."""
    if not allow_paid_providers:
        raise PermissionError("real-soft requires --allow-paid-providers")
    provider = content_pipeline.get_pipeline_provider()
    if provider.name == "mock":
        raise ValueError("real-soft requires an explicitly configured real LLM_PROVIDER")
    return [
        _result_summary(
            case["id"],
            content_pipeline.generate_candidate_round(case["brief"], provider=provider),
        )
        for case in load_brief_cases(path)
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("mock-hard", "real-soft"), nargs="?", default="mock-hard")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument(
        "--allow-paid-providers",
        action="store_true",
        help="acknowledge that real-soft can call the configured paid provider",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.mode == "real-soft" and not args.allow_paid_providers:
        parser.error("real-soft requires --allow-paid-providers")
    results = (
        evaluate_real_soft(args.cases, allow_paid_providers=True)
        if args.mode == "real-soft"
        else evaluate_mock_hard(args.cases)
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

