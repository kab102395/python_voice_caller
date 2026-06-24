from __future__ import annotations

import json
import logging
import re
from queue import Empty, Queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from clients import (
    download_binary,
    gather_verb,
    generate_twiml_response,
    say_verb,
    update_twilio_call_status,
    validate_twilio_signature,
)
from call_service import CallRequest, start_call
from config import get_settings
from engine import OpenAICompatibleReplyEngine, Reply, ReplyEngine, RuleBasedReplyEngine
from scenarios import DEFAULT_PATIENT_PROFILE, SCENARIOS


APP_NAME = "python_voice_caller"
ARTIFACT_ROOT = Path("artifacts")
LOG_ROOT = ARTIFACT_ROOT / "logs"
CURRENT_LOG_PATH = LOG_ROOT / "app.log"
TRANSCRIPT_ROOT = ARTIFACT_ROOT / "transcripts"
RECORDING_ROOT = ARTIFACT_ROOT / "recordings"
BUG_REPORT_ROOT = Path("bug_reports")
HARD_STOP_MESSAGE = "I have everything I need. Thank you for your help. Goodbye."
RUN_LABEL = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
CALL_EVENT_HISTORY_LIMIT = 200
LIVE_LOG_SOURCES = {
    "app": CURRENT_LOG_PATH,
    "uvicorn": LOG_ROOT / "launcher-uvicorn.log",
    "ngrok": LOG_ROOT / "launcher-ngrok.log",
}
INITIAL_OFFICE_STABILIZATION_MAX_FRAGMENTS = 1
INITIAL_OFFICE_STABILIZATION_MAX_CHARS = 100
TRUNCATED_OFFICE_TAILS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

OFFICE_DISCLAIMER_OPENERS = (
    "this call may be recorded for quality and training purposes",
    "this call may be recorded",
)
SHORT_COMPLETE_ACKS = {
    "hello",
    "hi",
    "i see",
    "no problem",
    "okay",
    "ok",
    "alright",
    "right",
    "sure",
    "thanks",
    "thank you",
    "fine",
    "good",
    "great",
}

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
    current_file_handler = RotatingFileHandler(
        CURRENT_LOG_PATH,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    current_file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(current_file_handler)


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


def office_speech_looks_truncated(speech: str) -> bool:
    cleaned = clean_text(speech)
    if not cleaned:
        return False
    lower = cleaned.lower()
    words = re.findall(r"[a-z0-9']+", lower)
    if not words:
        return False
    if lower.endswith(("...", ",", ":", ";", " -", "—", "–")):
        return True
    if len(words) >= 2 and words[-1] in TRUNCATED_OFFICE_TAILS:
        return True
    return False


def office_speech_looks_like_disclaimer_opener(speech: str) -> bool:
    cleaned = clean_text(speech).lower()
    if not cleaned:
        return False
    return any(cleaned.startswith(prefix) for prefix in OFFICE_DISCLAIMER_OPENERS)


def merge_overlapping_speech(left: str, right: str) -> str:
    left_clean = clean_text(left)
    right_clean = clean_text(right)
    if not left_clean:
        return right_clean
    if not right_clean:
        return left_clean
    left_tokens = re.findall(r"[a-z0-9']+", left_clean.lower())
    right_tokens = re.findall(r"[a-z0-9']+", right_clean.lower())
    max_overlap = min(len(left_tokens), len(right_tokens))
    for overlap in range(max_overlap, 0, -1):
        if left_tokens[-overlap:] == right_tokens[:overlap]:
            merged_tokens = re.findall(r"[a-z0-9']+", left_clean) + re.findall(
                r"[a-z0-9']+", right_clean
            )[overlap:]
            return " ".join(merged_tokens)
    if left_clean.endswith(right_clean) or right_clean.endswith(left_clean):
        return left_clean if len(left_clean) >= len(right_clean) else right_clean
    return f"{left_clean} {right_clean}".strip()


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


_LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _log_sort_key(line: str) -> str:
    m = _LOG_TS_RE.match(line)
    return m.group(1) if m else ""


def tail_text_file(path: Path, *, limit_lines: int = 120) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if limit_lines <= 0:
        return []
    return lines[-limit_lines:]


class CallEventHub:
    def __init__(self, *, history_limit: int = CALL_EVENT_HISTORY_LIMIT) -> None:
        self._history_limit = history_limit
        self._lock = threading.RLock()
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._subscribers: dict[str, list[Queue[dict[str, Any]]]] = {}

    def publish(self, call_sid: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "call_sid": call_sid,
            "event_type": event_type,
            "ts": utc_now(),
            **payload,
        }
        with self._lock:
            history = self._history.setdefault(call_sid, [])
            history.append(event)
            if len(history) > self._history_limit:
                del history[: len(history) - self._history_limit]
            for subscriber in self._subscribers.get(call_sid, []):
                subscriber.put_nowait(event)
        return event

    def snapshot(self, call_sid: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history.get(call_sid, []))

    def subscribe(self, call_sid: str) -> Queue[dict[str, Any]]:
        queue: Queue[dict[str, Any]] = Queue()
        with self._lock:
            self._subscribers.setdefault(call_sid, []).append(queue)
        return queue

    def unsubscribe(self, call_sid: str, queue: Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(call_sid)
            if not subscribers:
                return
            try:
                subscribers.remove(queue)
            except ValueError:
                return
            if not subscribers:
                self._subscribers.pop(call_sid, None)


call_event_hub = CallEventHub()


def format_sse_event(event: dict[str, Any]) -> str:
    data = json.dumps(event, sort_keys=True)
    return f"event: {event['event_type']}\ndata: {data}\n\n"


@dataclass
class CallMemory:
    scenario_id: str
    objective: str
    patient_profile: dict[str, str] = field(default_factory=dict)
    required_facts: list[str] = field(default_factory=list)
    optional_facts: list[str] = field(default_factory=list)
    phase: str = "opening"
    turn_count: int = 0
    recent_office_questions: list[str] = field(default_factory=list)
    recent_patient_answers: list[str] = field(default_factory=list)
    confirmed_facts: dict[str, str] = field(default_factory=dict)
    last_office_question: str | None = None
    last_patient_answer: str | None = None

    def tracked_fact_keys(self) -> set[str]:
        return {
            "first_name",
            "last_name",
            "date_of_birth",
            "phone",
            "callback_number",
            *self.required_facts,
            *self.optional_facts,
        }

    @classmethod
    def from_scenario(cls, scenario: dict[str, Any]) -> "CallMemory":
        profile = {
            str(key): str(value)
            for key, value in dict(scenario.get("patient_profile", DEFAULT_PATIENT_PROFILE)).items()
        }
        return cls(
            scenario_id=str(scenario.get("id", "unknown")),
            objective=str(scenario.get("objective", "")),
            patient_profile=profile,
            required_facts=[str(item) for item in scenario.get("required_facts", [])],
            optional_facts=[str(item) for item in scenario.get("optional_facts", [])],
        )

    def _append_limited(self, items: list[str], value: str, *, limit: int = 5) -> None:
        items.append(value)
        if len(items) > limit:
            del items[: len(items) - limit]

    def record_turn(self, *, speaker: str, text: str) -> None:
        self.turn_count += 1
        if speaker == "office":
            self.phase = "office_turn"
            self.last_office_question = text
            self._append_limited(self.recent_office_questions, text)
            return

        self.phase = "patient_turn"
        self.last_patient_answer = text
        self._append_limited(self.recent_patient_answers, text)
        lower = text.lower()
        tracked_keys = self.tracked_fact_keys()
        for key, value in self.patient_profile.items():
            if key not in tracked_keys:
                continue
            normalized_value = value.lower()
            if normalized_value and normalized_value in lower:
                self.confirmed_facts[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "objective": self.objective,
            "patient_profile": self.patient_profile,
            "required_facts": self.required_facts,
            "optional_facts": self.optional_facts,
            "phase": self.phase,
            "turn_count": self.turn_count,
            "recent_office_questions": self.recent_office_questions,
            "recent_patient_answers": self.recent_patient_answers,
            "confirmed_facts": self.confirmed_facts,
            "last_office_question": self.last_office_question,
            "last_patient_answer": self.last_patient_answer,
        }


@dataclass
class CallSession:
    call_sid: str
    scenario_id: str
    to_number: str
    from_number: str
    call_memory: "CallMemory"
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
        self.call_memory.record_turn(speaker=speaker, text=text)
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
            "call_memory": self.call_memory.to_dict(),
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
        lines.append(f"turn_count: {self.turn_count}")
        lines.append(f"call_memory_phase: {self.call_memory.phase}")
        if self.call_memory.required_facts:
            lines.append(
                "required_facts: "
                + ", ".join(self.call_memory.required_facts)
            )
        if self.call_memory.optional_facts:
            lines.append(
                "optional_facts: "
                + ", ".join(self.call_memory.optional_facts)
            )
        if self.call_memory.confirmed_facts:
            lines.append("confirmed_facts:")
            for key, value in self.call_memory.confirmed_facts.items():
                lines.append(f"  - {key}: {value}")
        if self.call_memory.recent_office_questions:
            lines.append("recent_office_questions:")
            for item in self.call_memory.recent_office_questions:
                lines.append(f"  - {item}")
        if self.call_memory.recent_patient_answers:
            lines.append("recent_patient_answers:")
            for item in self.call_memory.recent_patient_answers:
                lines.append(f"  - {item}")
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


def publish_call_event(session: CallSession, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = call_event_hub.publish(session.call_sid, event_type, payload)
    session.metadata.setdefault("event_counts", {})
    event_counts = session.metadata["event_counts"]
    if isinstance(event_counts, dict):
        event_counts[event_type] = int(event_counts.get(event_type, 0)) + 1
    session.metadata["last_event"] = event
    return event


def call_summary(session: CallSession) -> dict[str, Any]:
    return {
        "call_sid": session.call_sid,
        "scenario_id": session.scenario_id,
        "started_at": session.started_at,
        "updated_at": session.updated_at,
        "status": session.status,
        "turn_count": session.turn_count,
        "no_speech_count": session.no_speech_count,
        "elapsed_seconds": call_elapsed_seconds(session),
        "end_reason": session.end_reason,
        "recording_sid": session.recording_sid,
        "recording_url": session.recording_url,
        "recording_path": session.recording_path,
        "artifact_stem": session.artifact_stem(),
        "transcript_json_path": str(session.transcript_path()),
        "transcript_text_path": str(session.transcript_text_path()),
    }


def transcript_record_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data.get("turns", [])
    return {
        "call_sid": data.get("call_sid"),
        "scenario_id": data.get("scenario_id"),
        "started_at": data.get("started_at"),
        "updated_at": data.get("updated_at"),
        "status": data.get("status"),
        "turn_count": data.get("turn_count", len(turns)),
        "no_speech_count": data.get("no_speech_count", 0),
        "end_reason": data.get("end_reason"),
        "recording_sid": data.get("recording_sid"),
        "recording_url": data.get("recording_url"),
        "recording_path": data.get("recording_path"),
        "artifact_stem": path.stem,
        "transcript_json_path": str(path),
        "transcript_text_path": str(path.with_suffix(".txt")),
        "call_memory": data.get("call_memory", {}),
        "turns": turns,
        "metadata": data.get("metadata", {}),
    }


def transcript_summary_from_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    turns = data.get("turns", [])
    return {
        "call_sid": data.get("call_sid"),
        "scenario_id": data.get("scenario_id"),
        "started_at": data.get("started_at"),
        "updated_at": data.get("updated_at"),
        "status": data.get("status"),
        "turn_count": data.get("turn_count", len(turns)),
        "no_speech_count": data.get("no_speech_count", 0),
        "end_reason": data.get("end_reason"),
        "recording_sid": data.get("recording_sid"),
        "recording_path": data.get("recording_path"),
        "artifact_stem": path.stem,
        "transcript_json_path": str(path),
        "transcript_text_path": str(path.with_suffix(".txt")),
    }


def transcript_index(*, scenario_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(TRANSCRIPT_ROOT.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            summary = transcript_summary_from_file(path)
            if scenario_id and summary.get("scenario_id") != scenario_id:
                continue
            records.append(summary)
            if limit is not None and len(records) >= limit:
                break
        except Exception as exc:
            records.append(
                {
                    "artifact_stem": path.stem,
                    "transcript_json_path": str(path),
                    "error": str(exc),
                }
            )
    return records


def find_transcript_path(call_sid: str) -> Path | None:
    for path in TRANSCRIPT_ROOT.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("call_sid") == call_sid:
            return path
    return None


def resolve_call_record(call_sid: str) -> dict[str, Any]:
    session = get_session(call_sid)
    if session is not None:
        return {
            **call_summary(session),
            "call_memory": session.call_memory.to_dict(),
            "turns": session.turns,
            "metadata": session.metadata,
        }
    path = find_transcript_path(call_sid)
    if path is not None:
        return transcript_record_from_file(path)
    raise HTTPException(status_code=404, detail=f"Unknown call SID: {call_sid}")


def parse_frontmatter_markdown(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def parse_bug_index_md(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    bug_heading = re.compile(r"^##\s+Bug\s+(\d+)\s+[—-]\s+(.*)$")
    metadata_line = re.compile(r"^-\s+([^:]+):\s+(.*)$")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        heading_match = bug_heading.match(raw_line.strip())
        if heading_match:
            if current:
                items.append(current)
            current = {
                "id": int(heading_match.group(1)),
                "title": heading_match.group(2).strip(),
            }
            continue
        if current is None:
            continue
        metadata_match = metadata_line.match(raw_line.strip())
        if not metadata_match:
            continue
        key = metadata_match.group(1).strip().lower()
        value = metadata_match.group(2).strip()
        if key == "file":
            current["file"] = value.split("]", 1)[-1].strip("()") if value.startswith("[") else value
        elif key == "severity":
            current["severity"] = value
        elif key in {"scenario", "scenarios"}:
            current["scenario"] = value
    if current:
        items.append(current)
    return items


def bug_index() -> list[dict[str, Any]]:
    index_path = BUG_REPORT_ROOT / "INDEX.md"
    items = parse_bug_index_md(index_path) if index_path.exists() else []
    file_by_name = {path.name: path for path in BUG_REPORT_ROOT.glob("*.md")}
    for item in items:
        file_name = str(item.get("file", "")).strip()
        if file_name.startswith("[") and "](" in file_name:
            file_name = file_name.split("](", 1)[1].rstrip(")")
        path = file_by_name.get(file_name)
        if not path:
            continue
        fields = parse_frontmatter_markdown(path)
        if fields:
            item["id"] = int(fields.get("id", item["id"]))
            item["title"] = fields.get("title", item["title"])
            item["severity"] = fields.get("severity", item.get("severity", "Unknown"))
            item["scenario"] = fields.get("scenario", item.get("scenario", ""))
            item["call_sid"] = fields.get("call_sid", "")
            item["date"] = fields.get("date", "")
        item["file"] = str(path)
        item.setdefault("call_sid", "")
        item.setdefault("date", "")
        item.setdefault("severity", "Unknown")
        item.setdefault("scenario", "")
    items.sort(key=lambda item: item["id"])
    return items


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
    profile = dict(DEFAULT_PATIENT_PROFILE)
    profile.update(
        {
            str(key): str(value)
            for key, value in dict(context.get("patient_profile", {}) or {}).items()
        }
    )
    context["patient_profile"] = profile
    return context


def get_session(call_sid: str) -> CallSession | None:
    with _session_lock:
        return _sessions.get(call_sid)


def stop_live_call(call_sid: str, *, reason: str = "killed_by_user") -> dict[str, Any]:
    settings = get_settings()
    twilio_result = update_twilio_call_status(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        call_sid=call_sid,
        status="completed",
    )
    session = get_session(call_sid)
    if session and session.status != "completed":
        session.status = "completed"
        session.end_reason = reason
        session.updated_at = utc_now()
        session.metadata["stopped_by_user"] = True
        session.save()
        publish_call_event(
            session,
            "call_completed",
            {
                "status": "completed",
                "reason": reason,
                "call_sid": session.call_sid,
            },
        )
        log_event(
            "call_killed",
            {
                "call_sid": call_sid,
                "reason": reason,
                "scenario_id": session.scenario_id,
            },
        )
    return twilio_result


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
        scenario = scenario_context(scenario_id)
        if session is None:
            session = CallSession(
                call_sid=call_sid,
                scenario_id=scenario_id,
                to_number=to_number,
                from_number=from_number,
                call_memory=CallMemory.from_scenario(scenario),
                started_at=utc_now(),
                updated_at=utc_now(),
                metadata=metadata or {},
            )
            _sessions[call_sid] = session
            publish_call_event(
                session,
                "session_started",
                {
                    "scenario_id": session.scenario_id,
                    "to_number": session.to_number,
                    "from_number": session.from_number,
                },
            )
        else:
            session.scenario_id = scenario_id or session.scenario_id
            session.to_number = to_number or session.to_number
            session.from_number = from_number or session.from_number
            if session.call_memory.scenario_id != session.scenario_id:
                session.call_memory = CallMemory.from_scenario(scenario)
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
                timeout=14,
            ),
            "<Hangup/>",
        )

    return generate_twiml_response(
        gather_verb(
            action_url=action_url,
            prompt=prompt,
            voice=voice,
            timeout=14,
        ),
        say_verb("I couldn't hear a response. Goodbye.", voice=voice),
        "<Hangup/>",
    )


def _clear_initial_office_buffer(session: CallSession) -> None:
    session.metadata.pop("initial_office_buffer", None)
    session.metadata.pop("initial_office_buffer_count", None)
    session.metadata.pop("initial_office_buffer_updated_at", None)


# PGAI opens every call with a recorded disclaimer before the live agent speaks.
# Twilio sometimes delivers this as two rapid Gather results rather than one complete turn.
# This function holds the first fragment in a buffer and merges it with the next result
# so the bot always replies to the full greeting, not a cut-off disclaimer fragment.
def maybe_stage_office_speech(session: CallSession, speech: str) -> str | None:
    buffer_text = str(session.metadata.get("initial_office_buffer", "")).strip()
    fragment_count = int(session.metadata.get("initial_office_buffer_count", 0) or 0)
    combined = merge_overlapping_speech(buffer_text, speech)

    if fragment_count == 0 and office_speech_looks_like_disclaimer_opener(speech):
        cleaned = clean_text(combined)
        if len(cleaned) <= INITIAL_OFFICE_STABILIZATION_MAX_CHARS and not office_speech_looks_truncated(cleaned):
            session.metadata["initial_office_buffer"] = combined
            session.metadata["initial_office_buffer_count"] = 1
            session.metadata["initial_office_buffer_updated_at"] = utc_now()
            session.updated_at = utc_now()
            session.save()
            log_event(
                "office_speech_buffered",
                {
                    "call_sid": session.call_sid,
                    "scenario_id": session.scenario_id,
                    "fragment_count": 1,
                    "buffer_length": len(combined),
                },
            )
            return None
        return combined

    if office_speech_looks_truncated(speech) and fragment_count < 2 and len(combined) <= 180:
        session.metadata["initial_office_buffer"] = combined
        session.metadata["initial_office_buffer_count"] = fragment_count + 1
        session.metadata["initial_office_buffer_updated_at"] = utc_now()
        session.updated_at = utc_now()
        session.save()
        log_event(
            "office_speech_buffered",
            {
                "call_sid": session.call_sid,
                "scenario_id": session.scenario_id,
                "fragment_count": fragment_count + 1,
                "buffer_length": len(combined),
            },
        )
        return None

    if buffer_text:
        _clear_initial_office_buffer(session)
        return combined

    return speech


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
            return engine.initial_reply(scenario=scenario, call_memory=session.call_memory.to_dict())
        return engine.next_reply(
            scenario=scenario,
            transcript=session.turns,
            office_speech=office_speech,
            call_memory=session.call_memory.to_dict(),
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
            return fallback.initial_reply(scenario=scenario, call_memory=session.call_memory.to_dict())
        return fallback.next_reply(
            scenario=scenario,
            transcript=session.turns,
            office_speech=office_speech,
            call_memory=session.call_memory.to_dict(),
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
    session.pending_prompt = ""
    session.metadata.setdefault("webhook", {})["twiml"] = str(request.url)
    session.save()

    force_hangup, reason = should_force_hangup(session)
    if force_hangup:
        session.status = "completed"
        session.end_reason = reason
        session.save()
        publish_call_event(
            session,
            "call_completed",
            {
                "reason": session.end_reason,
                "status": session.status,
            },
        )
        return Response(
            content=render_hard_stop_twiml(voice=_settings.twilio_voice, reason=reason or "completed"),
            media_type="text/xml",
        )

    action_url = base_webhook_url("/voice")
    twiml_body = generate_twiml_response(
        gather_verb(
            action_url=f"{action_url}?call_sid={session.call_sid}&scenario={session.scenario_id}",
            prompt="",
            voice=_settings.twilio_voice,
            timeout=14,
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
        publish_call_event(
            session,
            "call_completed",
            {
                "reason": session.end_reason,
                "status": session.status,
            },
        )
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
            publish_call_event(
                session,
                "call_completed",
                {
                    "reason": session.end_reason,
                    "status": session.status,
                },
            )
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

    session.no_speech_count = 0
    staged_speech = maybe_stage_office_speech(session, speech)
    if staged_speech is None:
        session.updated_at = utc_now()
        session.save()
        return Response(
            content=generate_twiml_response(
                gather_verb(
                    action_url=f"{base_webhook_url('/voice')}?call_sid={session.call_sid}&scenario={session.scenario_id}",
                    prompt="",
                    voice=_settings.twilio_voice,
                    timeout=14,
                )
            ),
            media_type="text/xml",
        )
    speech = staged_speech

    session.add_turn(
        speaker="office",
        text=speech,
        raw={"Confidence": confidence, **params},
    )
    publish_call_event(
        session,
        "transcript_line",
        {
            "speaker": "office",
            "text": speech,
            "confidence": confidence or None,
            "direction": "inbound",
        },
    )

    reply = prompt_reply(session, speech)
    reply_text = clean_text(reply.text)
    session.add_turn(
        speaker="patient",
        text=reply_text,
        raw={"source": "engine", "should_hangup": reply.should_hangup},
    )
    publish_call_event(
        session,
        "transcript_line",
        {
            "speaker": "patient",
            "text": reply_text,
            "should_hangup": reply.should_hangup,
            "direction": "outbound",
        },
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
        publish_call_event(
            session,
            "call_completed",
            {
                "reason": session.end_reason,
                "status": session.status,
            },
        )
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
        call_status = params.get("CallStatus", session.status)
        previous_status = session.status
        status_events = session.metadata.setdefault("status_events", [])
        status_events.append({"ts": utc_now(), "params": params})
        if previous_status == "completed" and call_status != "completed":
            session.updated_at = utc_now()
            session.save()
            publish_call_event(
                session,
                "call_status",
                {
                    "call_status": previous_status,
                    "params": params,
                    "ignored": True,
                },
            )
        else:
            session.status = call_status
            session.updated_at = utc_now()
            session.save()
            publish_call_event(
                session,
                "call_status",
                {
                    "call_status": session.status,
                    "params": params,
                },
            )
            if call_status == "completed" and not session.end_reason:
                session.end_reason = "remote_hangup"
                session.save()
                publish_call_event(
                    session,
                    "call_completed",
                    {
                        "reason": "remote_hangup",
                        "status": "completed",
                    },
                )
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
            publish_call_event(
                session,
                "recording_ready",
                {
                    "recording_sid": recording_sid,
                    "recording_url": recording_url,
                    "recording_path": path,
                },
            )
        except Exception as exc:
            session.metadata["recording_download_error"] = str(exc)
        session.save()
    log_event("recording_status", params)
    return Response(content="ok", media_type="text/plain")


@app.get("/events/{call_sid}")
async def events(call_sid: str) -> StreamingResponse:
    queue = call_event_hub.subscribe(call_sid)
    backlog = call_event_hub.snapshot(call_sid)

    def stream() -> Iterable[str]:
        try:
            for event in backlog:
                yield format_sse_event(event)
            yield ": connected\n\n"
            while True:
                try:
                    event = queue.get(timeout=15)
                    yield format_sse_event(event)
                except Empty:
                    yield ": keepalive\n\n"
        finally:
            call_event_hub.unsubscribe(call_sid, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/scenarios")
async def api_scenarios() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": scenario_id,
                "objective": str(context.get("objective", "")),
                "starter": str(context.get("starter", "")),
                "required_facts": list(context.get("required_facts", [])),
                "optional_facts": list(context.get("optional_facts", [])),
            }
            for scenario_id, context in SCENARIOS.items()
        ]
    }


@app.post("/api/call")
async def api_call_start(body: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(body.get("scenario", "scheduling"))
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario_id}")
    request = CallRequest(
        scenario=scenario_id,
        target_number=_settings.allowed_target_number,
        dry_run=bool(body.get("dry_run", False)),
    )
    try:
        return start_call(request, emit_output=False)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/bugs")
async def api_bugs() -> dict[str, Any]:
    return {"items": bug_index()}


@app.get("/api/live-logs")
async def api_live_logs(source: str = "app", limit: int = 120) -> dict[str, Any]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    if source == "combined":
        items: list[dict[str, Any]] = []
        for name, path in LIVE_LOG_SOURCES.items():
            for line in tail_text_file(path, limit_lines=limit):
                items.append({"source": name, "line": line, "_ts": _log_sort_key(line)})
        items.sort(key=lambda x: x["_ts"])
        for item in items:
            del item["_ts"]
        return {"items": items[-limit:]}
    path = LIVE_LOG_SOURCES.get(source)
    if not path:
        raise HTTPException(status_code=400, detail=f"Unknown log source: {source}")
    return {
        "items": [
            {
                "source": source,
                "line": line,
            }
            for line in tail_text_file(path, limit_lines=limit)
        ]
    }


@app.get("/api/calls")
async def api_calls(limit: int = 50, scenario_id: str | None = None) -> dict[str, Any]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return {"items": transcript_index(scenario_id=scenario_id, limit=limit)}


@app.get("/api/calls/{call_sid}")
async def api_call(call_sid: str) -> dict[str, Any]:
    return resolve_call_record(call_sid)


@app.get("/api/calls/{call_sid}/transcript")
async def api_call_transcript(call_sid: str) -> dict[str, Any]:
    record = resolve_call_record(call_sid)
    return {
        "call_sid": record.get("call_sid"),
        "scenario_id": record.get("scenario_id"),
        "turns": record.get("turns", []),
        "call_memory": record.get("call_memory", {}),
        "metadata": record.get("metadata", {}),
        "transcript_json_path": record.get("transcript_json_path"),
        "transcript_text_path": record.get("transcript_text_path"),
    }


@app.post("/api/calls/{call_sid}/stop")
async def api_call_stop(call_sid: str) -> dict[str, Any]:
    session = get_session(call_sid)
    if session is not None and session.status == "completed":
        return {
            "call_sid": call_sid,
            "status": session.status,
            "end_reason": session.end_reason,
            "already_stopped": True,
        }
    try:
        update = stop_live_call(call_sid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "call_sid": call_sid,
        "status": update.get("status", "completed"),
        "end_reason": session.end_reason if session is not None else None,
        "already_stopped": False,
    }


@app.get("/dashboard")
async def dashboard() -> FileResponse:
    return FileResponse(Path("dashboard") / "index.html")


@app.get("/recordings/{filename}")
async def recording_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = RECORDING_ROOT / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Recording not found")
    return FileResponse(path, media_type="audio/mpeg", filename=safe_name)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": APP_NAME,
        "allowed_target_number": _settings.allowed_target_number,
        "base_url": _settings.base_url,
        "voice": _settings.twilio_voice,
        "max_turns": _settings.max_turns,
        "max_call_seconds": _settings.max_call_seconds,
        "engine": type(get_engine()).__name__,
        "event_stream": "/events/{call_sid}",
        "dashboard": "/dashboard",
        "api_call_start": "/api/call",
        "api_bugs": "/api/bugs",
        "api_calls": "/api/calls",
        "api_call": "/api/calls/{call_sid}",
        "api_scenarios": "/api/scenarios",
    }


if __name__ == "__main__":
    import uvicorn

    ensure_dirs()
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
