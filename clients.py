from __future__ import annotations

import base64
import html
import hashlib
import hmac
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


USER_AGENT = "python_voice_caller/0.2"


def _https_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def validate_twilio_signature(
    *,
    url: str,
    params: dict[str, str],
    signature: str | None,
    auth_token: str,
) -> bool:
    if not signature:
        return False
    normalized = url + "".join(f"{key}{value}" for key, value in sorted(params.items()))
    digest = hmac.new(
        auth_token.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def http_post_form(
    *,
    url: str,
    data: dict[str, str],
    basic_auth: tuple[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, str]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("User-Agent", USER_AGENT)
    if basic_auth:
        token = base64.b64encode(
            f"{basic_auth[0]}:{basic_auth[1]}".encode("utf-8")
        ).decode("utf-8")
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def http_post_json(
    *,
    url: str,
    data: dict[str, Any],
    bearer_token: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    encoded = json.dumps(data).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {bearer_token}")
    request.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def download_binary(
    *,
    url: str,
    basic_auth: tuple[str, str],
    timeout: float = 30.0,
) -> bytes:
    request = urllib.request.Request(url, method="GET")
    token = base64.b64encode(
        f"{basic_auth[0]}:{basic_auth[1]}".encode("utf-8")
    ).decode("utf-8")
    request.add_header("Authorization", f"Basic {token}")
    request.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


@dataclass(frozen=True)
class OutboundCallResult:
    sid: str
    status: str | None
    raw: dict[str, Any]


def create_twilio_call(
    *,
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    twiml_url: str,
    status_callback_url: str,
    recording_callback_url: str,
    timeout: float = 30.0,
) -> OutboundCallResult:
    form = {
        "From": from_number,
        "To": to_number,
        "Url": twiml_url,
        "Method": "POST",
        "StatusCallback": status_callback_url,
        "StatusCallbackEvent": "initiated ringing answered completed",
        "StatusCallbackMethod": "POST",
        "Record": "true",
        "RecordingStatusCallback": recording_callback_url,
        "RecordingStatusCallbackMethod": "POST",
        "RecordingStatusCallbackEvent": "completed",
    }
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(url, data=encoded, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("User-Agent", USER_AGENT)
    token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode(
        "utf-8"
    )
    request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_https_context()) as response:
            payload = response.read().decode("utf-8", errors="replace")
            raw = json.loads(payload)
            return OutboundCallResult(
                sid=raw["sid"],
                status=raw.get("status"),
                raw=raw,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Twilio call creation failed: HTTP {exc.code}: {body}") from exc


def generate_twiml_response(*verbs: str) -> str:
    return "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response>" + "".join(verbs) + "</Response>"


def say_verb(text: str, *, voice: str) -> str:
    escaped_text = html.escape(text, quote=False)
    escaped_voice = html.escape(voice, quote=True)
    return f"<Say voice=\"{escaped_voice}\">{escaped_text}</Say>"


def gather_verb(
    *,
    action_url: str,
    prompt: str,
    voice: str,
    timeout: int = 5,
    speech_timeout: int = 3,
    pause_seconds: int = 0,
) -> str:
    escaped_prompt = html.escape(prompt, quote=False)
    escaped_action_url = html.escape(action_url, quote=True)
    escaped_voice = html.escape(voice, quote=True)
    pause = f'<Pause length="{pause_seconds}"/>' if pause_seconds > 0 else ""
    return (
        f"<Gather input=\"speech\" action=\"{escaped_action_url}\" method=\"POST\" "
        f"speechTimeout=\"{speech_timeout}\" timeout=\"{timeout}\">"
        f"{pause}"
        f"<Say voice=\"{escaped_voice}\">{escaped_prompt}</Say>"
        "</Gather>"
    )
