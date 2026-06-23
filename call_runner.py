from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from clients import create_twilio_call
from config import get_settings
from scenarios import SCENARIOS


@dataclass(frozen=True)
class CallRequest:
    scenario: str
    target_number: str
    dry_run: bool = False


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


def validate_target_number(number: str, allowed: str) -> None:
    if number != allowed:
        raise SystemExit(
            f"Refusing to call {number!r}. This tool only allows {allowed}."
        )


def validate_base_url(base_url: str, *, dry_run: bool) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise SystemExit(f"BASE_URL must be a valid URL, got {base_url!r}")
    localhost_hosts = {"localhost", "127.0.0.1", "::1"}
    if not dry_run and parsed.scheme != "https":
        raise SystemExit(
            "Refusing to place a live call without an https BASE_URL. "
            "Use a public tunnel URL."
        )
    if not dry_run and parsed.hostname in localhost_hosts:
        raise SystemExit(
            "Refusing to place a live call against localhost. "
            "Use a public tunnel URL."
        )


def start_call(request: CallRequest) -> None:
    settings = get_settings()
    validate_target_number(request.target_number, settings.allowed_target_number)
    validate_base_url(settings.base_url, dry_run=request.dry_run)

    twiml_url = f"{settings.base_url.rstrip('/')}/twiml?{urlencode({'scenario': request.scenario})}"
    status_callback = f"{settings.base_url.rstrip('/')}/status"
    recording_callback = f"{settings.base_url.rstrip('/')}/recording-status"

    payload = {
        "scenario": request.scenario,
        "to": request.target_number,
        "from": settings.twilio_phone_number,
        "twiml_url": twiml_url,
        "status_callback": status_callback,
        "recording_callback": recording_callback,
    }

    if request.dry_run:
        print(json.dumps(payload, indent=2))
        return

    result = create_twilio_call(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        from_number=settings.twilio_phone_number,
        to_number=request.target_number,
        twiml_url=twiml_url,
        status_callback_url=status_callback,
        recording_callback_url=recording_callback,
    )
    print(
        json.dumps(
            {
                "sid": result.sid,
                "status": result.status,
                "scenario": request.scenario,
                "to": request.target_number,
                "from": settings.twilio_phone_number,
            },
            indent=2,
        )
    )


def main() -> int:
    settings = get_settings()
    args = parse_args()
    target = args.to or settings.allowed_target_number
    request = CallRequest(
        scenario=args.scenario,
        target_number=target,
        dry_run=args.dry_run,
    )
    start_call(request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
