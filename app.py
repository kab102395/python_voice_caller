from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from clients import (
    download_binary,
    gather_verb,
    generate_twiml_response,
    say_verb,
    validate_twilio_signature,
)
from config import get_settings
from engine import OpenAICompatibleReplyEngine, Reply, ReplyEngine, RuleBasedReplyEngine
from scenarios import SCENARIOS


APP_NAME = "python_voice_caller"
ARTIFACT_ROOT = Path("artifacts")
LOG_ROOT = ARTIFACT_ROOT / "logs"
TRANSCRIPT_ROOT = ARTIFACT_ROOT / "transcripts"
RECORDING_ROOT = ARTIFACT_ROOT / "recordings"
HARD_STOP_MESSAGE = "I have everything I need. Thank you for your help. Goodbye."
RUN_LABEL = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in (LOG_ROOT, TRANSCRIPT_ROOT, RECORDING_ROOT):
        path.mkdir(parents=True, exist_ok=True)


ensure_dirs()

logger = logging.getLogger(APP_NAME)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(console_handler)
    file_handler = RotatingFileHandler(
        LOG_ROOT / f"app-{RUN_LABEL}.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(file_handler)


app = FastAPI(title="Python Voice Caller")
_settings = get_settings()
_session_lock = threading.RLock()
_sessions: dict[str, "CallSession"] = {}
_engine: ReplyEngine | None = None
_engine_disabled_reason: str | None = None


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def clean_text(text: str, *, max_chars: int = 400) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) > max_chars:
        compact = compact[: max_chars - 3].rstrip() + "..."
    return compact


def parse_iso_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def call_elapsed_seconds(session: CallSession) -> int:
    started_at = parse_iso_timestamp(session.started_at)
    delta = datetime.now(timezone.utc) - started_at
    return max(0, int(delta.total_seconds()))


def should_force_hangup(session: CallSession) -> tuple[bool, str | None]:
    if session.status == "completed":
        return True, session.end_reason or "completed"
    if session.turn_count >= _settings.max_turns * 2:
        return True, "max_turns_reached"
    if call_elapsed_seconds(session) >= _settings.max_call_seconds:
        return True, "max_call_seconds_reached"
    return False, None


async def read_form_fields(request: Request) -> dict[str, str]:
    body = await request.body()
    raw = body.decode("utf-8", errors="replace")
    parsed: dict[str, str] = {}
    for key, value in parse_qsl(raw, keep_blank_values=True):
        parsed[key] = value
    return parsed


def webhook_signature_ok(request: Request, params: dict[str, str]) -> bool:
    signature = request.headers.get("x-twilio-signature")
    if not signature:
        return False
    return validate_twilio_signature(
        url=str(request.url),
        params=params,
        signature=signature,
        auth_token=_settings.twilio_auth_token,
    )


def validate_and_log_request(request: Request, params: dict[str, str]) -> None:
    if not webhook_signature_ok(request, params):
        log_event(
            "twilio_signature_rejected",
            {"path": str(request.url.path), "keys": sorted(params.keys())},
        )
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def log_event(event: str, payload: dict[str, Any]) -> None:
    logger.info("%s %s", event, json.dumps(payload, sort_keys=True))


@dataclass
class CallSession:
    call_sid: str
    scenario_id: str
    to_number: str
    from_number: str
    started_at: str
    updated_at: str
    status: str = "started"
    turn_count: int = 0
    no_speech_count: int = 0
    pending_prompt: str | None = None
    recording_sid: str | None = None
    recording_url: str | None = None
    recording_path: str | None = None
    end_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    turns: list[dict[str, Any]] = field(default_factory=list)

    def add_turn(self, *, speaker: str, text: str, raw: dict[str, Any] | None = None) -> None:
        self.turns.append(
            {
                "speaker": speaker,
                "text": text,
                "raw": raw or {},
                "ts": utc_now(),
            }
        )
        self.updated_at = utc_now()
        self.turn_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_sid": self.call_sid,
            "scenario_id": self.scenario_id,
            "to_number": self.to_number,
            "from_number": self.from_number,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "turn_count": self.turn_count,
            "no_speech_count": self.no_speech_count,
            "pending_prompt": self.pending_prompt,
            "recording_sid": self.recording_sid,
            "recording_url": self.recording_url,
            "recording_path": self.recording_path,
            "end_reason": self.end_reason,
            "metadata": self.metadata,
            "turns": self.turns,
        }

    def transcript_path(self) -> Path:
        return TRANSCRIPT_ROOT / f"{self.artifact_stem()}.json"

    def transcript_text_path(self) -> Path:
        return TRANSCRIPT_ROOT / f"{self.artifact_stem()}.txt"

    def artifact_stem(self) -> str:
        started = self.started_at.replace(":", "").replace("-", "")
        started = started.replace("+00:00", "").replace("Z", "")
        started = started.replace("T", "-").split(".")[0]
        scenario = self.scenario_id.replace("_", "-")
        return f"{started}_{scenario}_{self.call_sid[:8]}"

    def render_transcript_text(self) -> str:
        lines: list[str] = []
        lines.append(f"call_sid: {self.call_sid}")
        lines.append(f"scenario_id: {self.scenario_id}")
        lines.append(f"from_number: {self.from_number}")
        lines.append(f"to_number: {self.to_number}")
        lines.append(f"started_at: {self.started_at}")
        lines.append(f"updated_at: {self.updated_at}")
        lines.append(f"status: {self.status}")
        if self.end_reason:
            lines.append(f"end_reason: {self.end_reason}")
        if self.recording_path:
            lines.append(f"recording_path: {self.recording_path}")
        lines.append("")
        lines.append("turns:")
        if not self.turns:
            lines.append("  (none)")
        else:
            for idx, turn in enumerate(self.turns, start=1):
                speaker = str(turn.get("speaker", "unknown")).upper()
                timestamp = str(turn.get("ts", ""))
                text = str(turn.get("text", "")).strip()
                lines.append(f"{idx}. [{timestamp}] {speaker}: {text}")
        lines.append("")
        return "\n".join(lines)

    def save(self) -> None:
        atomic_write_text(self.transcript_path(), json.dumps(self.to_dict(), indent=2))
        atomic_write_text(self.transcript_text_path(), self.render_transcript_text())


def get_engine() -> ReplyEngine:
    global _engine
    if _engine is not None:
        return _engine
    if _settings.llm_api_key:
        _engine = OpenAICompatibleReplyEngine(
            api_base=_settings.llm_api_base,
            api_key=_settings.llm_api_key,
            model=_settings.llm_model,
            timeout_seconds=_settings.llm_timeout_seconds,
        )
    else:
        _engine = RuleBasedReplyEngine()
    return _engine


def scenario_context(scenario_id: str) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise KeyError(f"Unknown scenario: {scenario_id}")
    context = dict(SCENARIOS[scenario_id])
    context["id"] = scenario_id
    context["max_turns"] = _settings.max_turns
    return context


def get_session(call_sid: str) -> CallSession | None:
    with _session_lock:
        return _sessions.get(call_sid)


def upsert_session(
    *,
    call_sid: str,
    scenario_id: str,
    to_number: str,
    from_number: str,
    metadata: dict[str, Any] | None = None,
) -> CallSession:
    with _session_lock:
        session = _sessions.get(call_sid)
        if session is None:
            session = CallSession(
                call_sid=call_sid,
                scenario_id=scenario_id,
                to_number=to_number,
                from_number=from_number,
                started_at=utc_now(),
                updated_at=utc_now(),
                metadata=metadata or {},
            )
            _sessions[call_sid] = session
        else:
            session.scenario_id = scenario_id or session.scenario_id
            session.to_number = to_number or session.to_number
            session.from_number = from_number or session.from_number
            if metadata:
                session.metadata.update(metadata)
            session.updated_at = utc_now()
        session.save()
        return session


def render_turn_twiml(
    *,
    prompt: str,
    action_url: str,
    voice: str,
    no_speech_retry: bool,
    retry_prompt: str | None = None,
    final: bool = False,
) -> str:
    if final:
        return generate_twiml_response(
            say_verb(prompt, voice=voice),
            "<Hangup/>",
        )

    if no_speech_retry:
        return generate_twiml_response(
            say_verb("Sorry, I didn't catch that. Let's try once more.", voice=voice),
            gather_verb(
                action_url=action_url,
                prompt=retry_prompt or prompt,
                voice=voice,
                timeout=15,
            ),
            "<Hangup/>",
        )

    return generate_twiml_response(
        gather_verb(
            action_url=action_url,
            prompt=prompt,
            voice=voice,
            timeout=15,
        ),
        say_verb("I couldn't hear a response. Goodbye.", voice=voice),
        "<Hangup/>",
    )


def render_hard_stop_twiml(*, voice: str, reason: str) -> str:
    log_event("call_hard_stop", {"reason": reason})
    return generate_twiml_response(
        say_verb(HARD_STOP_MESSAGE, voice=voice),
        "<Hangup/>",
    )


def sanitized_target_number(value: str) -> str:
    if value != _settings.allowed_target_number:
        raise RuntimeError(
            f"Refusing unexpected destination number {value!r}; only "
            f"{_settings.allowed_target_number} is allowed."
        )
    return value


def base_webhook_url(path: str) -> str:
    return f"{_settings.base_url.rstrip('/')}{path}"


def build_session_from_webhook(
    params: dict[str, str], *, fallback_scenario: str | None = None
) -> CallSession:
    call_sid = params.get("CallSid") or params.get("callSid") or "unknown"
    scenario_id = params.get("scenario") or fallback_scenario or "scheduling"
    to_number = params.get("To") or _settings.allowed_target_number
    from_number = params.get("From") or _settings.twilio_phone_number
    sanitized_target_number(to_number)
    return upsert_session(
        call_sid=call_sid,
        scenario_id=scenario_id,
        to_number=to_number,
        from_number=from_number,
        metadata={"source": "twilio"},
    )


def prompt_reply(session: CallSession, office_speech: str | None = None) -> Reply:
    global _engine, _engine_disabled_reason
    scenario = scenario_context(session.scenario_id)
    engine = get_engine()
    try:
        if office_speech is None:
            return engine.initial_reply(scenario=scenario)
        return engine.next_reply(
            scenario=scenario,
            transcript=session.turns,
            office_speech=office_speech,
        )
    except Exception as exc:
        error_text = str(exc)
        quota_error = any(
            marker in error_text
            for marker in ("HTTP 429", "RESOURCE_EXHAUSTED", "quota", "rate limit")
        )
        if quota_error:
            if _engine_disabled_reason != "quota":
                log_event(
                    "reply_engine_disabled",
                    {
                        "call_sid": session.call_sid,
                        "scenario_id": session.scenario_id,
                        "reason": "quota",
                        "error": error_text,
                    },
                )
            _engine_disabled_reason = "quota"
            _engine = RuleBasedReplyEngine()
        else:
            log_event(
                "reply_engine_failed",
                {
                    "call_sid": session.call_sid,
                    "scenario_id": session.scenario_id,
                    "error": error_text,
                },
            )
        fallback = RuleBasedReplyEngine()
        if office_speech is None:
            return fallback.initial_reply(scenario=scenario)
        return fallback.next_reply(
            scenario=scenario,
            transcript=session.turns,
            office_speech=office_speech,
        )


def save_recording_artifact(session: CallSession, recording_sid: str, recording_url: str) -> str:
    if not recording_sid:
        raise RuntimeError("Missing recording SID")
    url = recording_url.rstrip("/")
    if not url.endswith(".mp3"):
        url = f"{url}.mp3"
    recording_bytes = download_binary(
        url=url,
        basic_auth=(_settings.twilio_account_sid, _settings.twilio_auth_token),
        timeout=45.0,
    )
    path = RECORDING_ROOT / f"{session.artifact_stem()}_{recording_sid}.mp3"
    path.write_bytes(recording_bytes)
    return str(path)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now()}


@app.post("/twiml")
async def twiml(request: Request) -> Response:
    params = await read_form_fields(request)
    validate_and_log_request(request, params)
    session = build_session_from_webhook(
        params, fallback_scenario=request.query_params.get("scenario")
    )
    opening = prompt_reply(session)
    session.pending_prompt = clean_text(opening.text)
    session.metadata.setdefault("webhook", {})["twiml"] = str(request.url)
    session.save()

    force_hangup, reason = should_force_hangup(session)
    if force_hangup:
        session.status = "completed"
        session.end_reason = reason
        session.save()
        return Response(
            content=render_hard_stop_twiml(voice=_settings.twilio_voice, reason=reason or "completed"),
            media_type="text/xml",
        )

    action_url = base_webhook_url("/voice")
    twiml_body = generate_twiml_response(
        gather_verb(
            action_url=f"{action_url}?call_sid={session.call_sid}&scenario={session.scenario_id}",
            prompt=session.pending_prompt,
            voice=_settings.twilio_voice,
            timeout=15,
        ),
        say_verb("I couldn't hear a response. Goodbye.", voice=_settings.twilio_voice),
        "<Hangup/>",
    )
    log_event(
        "twiml_start",
        {
            "call_sid": session.call_sid,
            "scenario_id": session.scenario_id,
            "to": session.to_number,
        },
    )
    return Response(content=twiml_body, media_type="text/xml")


@app.post("/voice")
async def voice(request: Request) -> Response:
    params = await read_form_fields(request)
    validate_and_log_request(request, params)
    session = build_session_from_webhook(
        params, fallback_scenario=request.query_params.get("scenario")
    )

    force_hangup, reason = should_force_hangup(session)
    if force_hangup:
        session.status = "completed"
        session.end_reason = reason
        session.save()
        return Response(
            content=render_hard_stop_twiml(voice=_settings.twilio_voice, reason=reason or "completed"),
            media_type="text/xml",
        )

    speech = clean_text(params.get("SpeechResult", ""))
    confidence = params.get("Confidence", "").strip()
    if not speech:
        session.no_speech_count += 1
        session.updated_at = utc_now()
        session.save()
        if session.no_speech_count >= 2:
            session.status = "completed"
            session.end_reason = "no_speech_timeout"
            session.save()
            return Response(
                content=render_hard_stop_twiml(
                    voice=_settings.twilio_voice,
                    reason="no_speech_timeout",
                ),
                media_type="text/xml",
            )

        retry_prompt = session.pending_prompt or "Sorry, I didn't catch that. Could you repeat it?"
        body = render_turn_twiml(
            prompt=retry_prompt,
            action_url=f"{base_webhook_url('/voice')}?call_sid={session.call_sid}&scenario={session.scenario_id}",
            voice=_settings.twilio_voice,
            no_speech_retry=True,
            retry_prompt=retry_prompt,
        )
        return Response(content=body, media_type="text/xml")

    session.add_turn(
        speaker="office",
        text=speech,
        raw={"Confidence": confidence, **params},
    )

    reply = prompt_reply(session, speech)
    reply_text = clean_text(reply.text)
    session.add_turn(
        speaker="patient",
        text=reply_text,
        raw={"source": "engine", "should_hangup": reply.should_hangup},
    )
    session.pending_prompt = reply_text
    session.updated_at = utc_now()
    if reply.should_hangup or should_force_hangup(session)[0]:
        session.status = "completed"
        if reply.should_hangup:
            session.end_reason = reply_text
        else:
            session.end_reason = should_force_hangup(session)[1] or "max_turns_reached"
        session.save()
        body = generate_twiml_response(
            say_verb(reply_text, voice=_settings.twilio_voice),
            "<Hangup/>",
        )
        log_event(
            "voice_end",
            {
                "call_sid": session.call_sid,
                "scenario_id": session.scenario_id,
                "reason": session.end_reason,
            },
        )
        return Response(content=body, media_type="text/xml")

    session.save()
    body = render_turn_twiml(
        prompt=reply_text,
        action_url=f"{base_webhook_url('/voice')}?call_sid={session.call_sid}&scenario={session.scenario_id}",
        voice=_settings.twilio_voice,
        no_speech_retry=False,
    )
    log_event(
        "voice_turn",
        {
            "call_sid": session.call_sid,
            "scenario_id": session.scenario_id,
            "speech": speech,
            "reply": reply_text,
        },
    )
    return Response(content=body, media_type="text/xml")


@app.post("/status")
async def status(request: Request) -> Response:
    params = await read_form_fields(request)
    validate_and_log_request(request, params)
    session = get_session(params.get("CallSid", ""))
    if session:
        session.status = params.get("CallStatus", session.status)
        session.updated_at = utc_now()
        session.metadata.setdefault("status_events", []).append(
            {"ts": utc_now(), "params": params}
        )
        session.save()
    log_event("call_status", params)
    return Response(content="ok", media_type="text/plain")


@app.post("/recording-status")
async def recording_status(request: Request) -> Response:
    params = await read_form_fields(request)
    validate_and_log_request(request, params)
    call_sid = params.get("CallSid", "")
    recording_sid = params.get("RecordingSid", "")
    recording_url = params.get("RecordingUrl", "")
    session = get_session(call_sid)
    if session and recording_sid and recording_url:
        session.recording_sid = recording_sid
        session.recording_url = recording_url
        session.updated_at = utc_now()
        try:
            path = save_recording_artifact(session, recording_sid, recording_url)
            session.recording_path = path
        except Exception as exc:
            session.metadata["recording_download_error"] = str(exc)
        session.save()
    log_event("recording_status", params)
    return Response(content="ok", media_type="text/plain")


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "allowed_target_number": _settings.allowed_target_number,
        "voice": _settings.twilio_voice,
        "max_turns": _settings.max_turns,
        "max_call_seconds": _settings.max_call_seconds,
        "engine": type(get_engine()).__name__,
    }


if __name__ == "__main__":
    import uvicorn

    ensure_dirs()
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
