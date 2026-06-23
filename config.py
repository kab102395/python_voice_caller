from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

try:  # pragma: no cover - optional convenience dependency
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - fallback when python-dotenv is absent
    load_dotenv = None


if load_dotenv is not None:  # pragma: no cover - import side effect
    load_dotenv()


E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")
ACCOUNT_SID_RE = re.compile(r"^AC[0-9a-fA-F]{32}$")


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    base_url: str
    allowed_target_number: str
    llm_api_key: str | None
    llm_api_base: str
    llm_model: str
    llm_timeout_seconds: float
    twilio_voice: str
    max_turns: int
    max_call_seconds: int


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _validate_e164(label: str, value: str) -> str:
    if not E164_RE.fullmatch(value):
        raise RuntimeError(f"{label} must be an E.164 number, got: {value!r}")
    return value


def _normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError("BASE_URL must start with http:// or https://")
    if not parsed.netloc:
        raise RuntimeError("BASE_URL must include a hostname")
    return value.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    twilio_account_sid = _require("TWILIO_ACCOUNT_SID")
    if not ACCOUNT_SID_RE.fullmatch(twilio_account_sid):
        raise RuntimeError("TWILIO_ACCOUNT_SID does not look valid")

    twilio_auth_token = _require("TWILIO_AUTH_TOKEN")
    twilio_phone_number = _validate_e164(
        "TWILIO_PHONE_NUMBER", _require("TWILIO_PHONE_NUMBER")
    )
    base_url = _normalize_base_url(_require("BASE_URL"))
    allowed_target_number = _validate_e164(
        "ALLOWED_TARGET_NUMBER", os.getenv("ALLOWED_TARGET_NUMBER", "+18054398008")
    )

    llm_api_base = _normalize_base_url(
        os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    )
    llm_api_key = _optional("LLM_API_KEY")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    llm_timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    twilio_voice = os.getenv("TWILIO_VOICE", "Google.en-US-Chirp3-HD-Puck").strip() or "Google.en-US-Chirp3-HD-Puck"
    max_turns = int(os.getenv("MAX_CALL_TURNS", "30"))
    if max_turns < 1 or max_turns > 50:
        raise RuntimeError("MAX_CALL_TURNS must be between 1 and 50")
    max_call_seconds = int(os.getenv("MAX_CALL_SECONDS", "240"))
    if max_call_seconds < 30 or max_call_seconds > 3600:
        raise RuntimeError("MAX_CALL_SECONDS must be between 30 and 3600")

    return Settings(
        twilio_account_sid=twilio_account_sid,
        twilio_auth_token=twilio_auth_token,
        twilio_phone_number=twilio_phone_number,
        base_url=base_url,
        allowed_target_number=allowed_target_number,
        llm_api_key=llm_api_key,
        llm_api_base=llm_api_base,
        llm_model=llm_model,
        llm_timeout_seconds=llm_timeout_seconds,
        twilio_voice=twilio_voice,
        max_turns=max_turns,
        max_call_seconds=max_call_seconds,
    )
