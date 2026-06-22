from __future__ import annotations

import argparse

from call_service import CallRequest, start_call
from config import get_settings
from scenarios import SCENARIOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a challenge voice call.")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        default="scheduling",
        help="Scenario to run.",
    )
    parser.add_argument(
        "--to",
        default=None,
        help="Destination number. Defaults to the challenge allowlist number.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the call payload without creating the call.",
    )
    return parser.parse_args()


def main() -> int:
    settings = get_settings()
    args = parse_args()
    target = args.to or settings.allowed_target_number
    request = CallRequest(
        scenario=args.scenario,
        target_number=target,
        dry_run=args.dry_run,
    )
    start_call(request, emit_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
