from __future__ import annotations

import argparse
import json

from call_runner import CallRequest, start_call
from config import get_settings
from scenarios import SCENARIOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all challenge scenarios sequentially.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print each call payload without placing live calls.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=len(SCENARIOS),
        help="Maximum number of scenarios to run.",
    )
    return parser.parse_args()


def iter_batch_scenarios(limit: int | None = None) -> list[str]:
    scenario_names = list(SCENARIOS.keys())
    if limit is None:
        return scenario_names
    if limit < 0:
        raise ValueError("limit must be non-negative")
    return scenario_names[:limit]


def build_requests(*, dry_run: bool, limit: int | None = None) -> list[CallRequest]:
    settings = get_settings()
    requests: list[CallRequest] = []
    for scenario in iter_batch_scenarios(limit):
        requests.append(
            CallRequest(
                scenario=scenario,
                target_number=settings.allowed_target_number,
                dry_run=dry_run,
            )
        )
    return requests


def main() -> int:
    args = parse_args()
    requests = build_requests(dry_run=args.dry_run, limit=args.limit)
    for index, request in enumerate(requests, start=1):
        print(json.dumps({"index": index, "scenario": request.scenario}, indent=2))
        start_call(request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
