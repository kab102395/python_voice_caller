from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from collections import Counter
from pathlib import Path
from typing import Any

from clients import http_post_json
from scenarios import build_patient_prompt


GOODBYE_RE = re.compile(r"\b(bye|goodbye|see you|take care|have a good day|have a great day)\b", re.I)
WRAP_UP_RE = re.compile(r"\b(is there anything else|anything else I can help|anything else for you)\b", re.I)
# Prevents premature hangup when PGAI asks a mid-call confirmation question.
# Without this, the LLM mistakes "is that correct?" for a closing cue and hangs up before the booking completes.
CONFIRMATION_RE = re.compile(r"\b(is that correct|is this correct|is all (of )?that correct|does that (sound|look) right|is this the (appointment|one)|is that the (appointment|one))\b", re.I)
REPETITION_GUARD_REPLY = "I think we've already covered that. What would you like me to do next?"
CONFIRMATION_VARIANTS = (
    "Yes, that's correct.",
    "That's right.",
    "Yes, that looks right.",
    "Correct.",
)
GOODBYE_VARIANTS = (
    "Thanks, that helps. Bye.",
    "Okay, thank you. Bye.",
    "Thanks, bye.",
)
WRAP_UP_VARIANTS = (
    "No, that's all I needed. Thanks, bye!",
    "That's everything for me. Thanks, bye.",
    "No, I'm good. Thanks. Bye.",
)
INSURANCE_BRING_VARIANTS = (
    "Just my insurance card, if you need it.",
    "I can bring my insurance card if you want.",
    "Do you want me to bring my card?",
)
INSURANCE_CONFIRM_VARIANTS = (
    "Yes, I have Blue Cross PPO.",
    "I have Blue Cross PPO.",
    "That's the insurance I have.",
)
IDENTITY_CORRECTION_VARIANTS = (
    "My date of birth is January 12, 1990.",
    "No, that's not right. My date of birth is January 12, 1990.",
    "I've said January 12, 1990. Can we move on?",
)
HUMAN_HANDOFF_VARIANTS = (
    "I really do need a person to help me with this.",
    "Can you transfer me to someone who can help?",
    "Please have a staff member call me back.",
)


def _normalize_variant_seed(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _last_patient_turn(transcript: list[dict[str, str]]) -> str:
    for turn in reversed(transcript):
        if turn.get("speaker") == "patient":
            return str(turn.get("text", ""))
    return ""


def _variant_index(
    *,
    branch: str,
    variants: tuple[str, ...],
    office_speech: str,
    transcript: list[dict[str, str]],
    call_memory: dict[str, Any] | None,
) -> int:
    memory = call_memory or {}
    seed = "|".join(
        (
            branch,
            str(memory.get("scenario_id", "")),
            str(memory.get("turn_count", len(transcript))),
            str(len(transcript)),
            _normalize_variant_seed(office_speech),
        )
    )
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % len(variants)


def _branch_reply(
    *,
    branch: str,
    variants: tuple[str, ...],
    office_speech: str,
    transcript: list[dict[str, str]],
    call_memory: dict[str, Any] | None,
    should_hangup: bool,
) -> Reply:
    index = _variant_index(
        branch=branch,
        variants=variants,
        office_speech=office_speech,
        transcript=transcript,
        call_memory=call_memory,
    )
    return Reply(text=variants[index], should_hangup=should_hangup)


def _guardrail_reply(
    *,
    transcript: list[dict[str, str]],
    office_speech: str,
    call_memory: dict[str, Any] | None = None,
) -> Reply | None:
    if _repetition_detected(transcript):
        return Reply(text=REPETITION_GUARD_REPLY)
    if CONFIRMATION_RE.search(office_speech):
        return _branch_reply(
            branch="confirmation",
            variants=CONFIRMATION_VARIANTS,
            office_speech=office_speech,
            transcript=transcript,
            call_memory=call_memory,
            should_hangup=False,
        )
    if GOODBYE_RE.search(office_speech):
        return _branch_reply(
            branch="goodbye",
            variants=GOODBYE_VARIANTS,
            office_speech=office_speech,
            transcript=transcript,
            call_memory=call_memory,
            should_hangup=True,
        )
    if WRAP_UP_RE.search(office_speech) and len(transcript) >= 6:
        return _branch_reply(
            branch="wrap_up",
            variants=WRAP_UP_VARIANTS,
            office_speech=office_speech,
            transcript=transcript,
            call_memory=call_memory,
            should_hangup=True,
        )
    return None


def _is_echo_reply(reply_text: str, office_speech: str, last_patient_text: str) -> bool:
    normalized_reply = _normalize_text(reply_text)
    normalized_office = _normalize_text(office_speech)
    normalized_last_patient = _normalize_text(last_patient_text)
    if not normalized_reply:
        return True
    if normalized_reply == normalized_office or normalized_reply == normalized_last_patient:
        return True
    if _similarity(reply_text, office_speech) >= 0.72:
        return True
    if last_patient_text and _similarity(reply_text, last_patient_text) >= 0.88:
        return True
    return False


def _dob_challenge_detected(office_speech: str) -> bool:
    lower = office_speech.lower()
    return "date of birth" in lower or "birthday" in lower or bool(re.search(r"\b\d{4}\b", lower))


def _shape_model_reply(
    *,
    scenario: dict[str, Any],
    transcript: list[dict[str, str]],
    office_speech: str,
    call_memory: dict[str, Any] | None,
    reply_text: str,
) -> str:
    scenario_id = str(scenario.get("id", "")).strip()
    last_patient_text = _last_patient_turn(transcript)
    patient_turns = sum(1 for turn in transcript if turn.get("speaker") == "patient")

    if scenario_id == "insurance":
        office_lower = office_speech.lower()
        if any(phrase in office_lower for phrase in ("bring", "need to bring", "anything with me")):
            index = _variant_index(
                branch="insurance_bring",
                variants=INSURANCE_BRING_VARIANTS,
                office_speech=office_speech,
                transcript=transcript,
                call_memory=call_memory,
            )
            return INSURANCE_BRING_VARIANTS[index]
        if "insurance" in office_lower or "plan" in office_lower:
            index = _variant_index(
                branch="insurance_confirm",
                variants=INSURANCE_CONFIRM_VARIANTS,
                office_speech=office_speech,
                transcript=transcript,
                call_memory=call_memory,
            )
            return INSURANCE_CONFIRM_VARIANTS[index]
        if _is_echo_reply(reply_text, office_speech, last_patient_text):
            return INSURANCE_CONFIRM_VARIANTS[
                _variant_index(
                    branch="insurance_echo",
                    variants=INSURANCE_CONFIRM_VARIANTS,
                    office_speech=office_speech,
                    transcript=transcript,
                    call_memory=call_memory,
                )
            ]

    if scenario_id == "identity_wrong_dob_persistent" and _dob_challenge_detected(office_speech):
        index = min(patient_turns, len(IDENTITY_CORRECTION_VARIANTS) - 1)
        return IDENTITY_CORRECTION_VARIANTS[index]

    if scenario_id == "escalation_demands_human":
        office_lower = office_speech.lower()
        if any(phrase in office_lower for phrase in ("human", "person", "robot", "transfer")):
            index = min(patient_turns, len(HUMAN_HANDOFF_VARIANTS) - 1)
            return HUMAN_HANDOFF_VARIANTS[index]
        if _is_echo_reply(reply_text, office_speech, last_patient_text):
            index = min(patient_turns, len(HUMAN_HANDOFF_VARIANTS) - 1)
            return HUMAN_HANDOFF_VARIANTS[index]

    if _is_echo_reply(reply_text, office_speech, last_patient_text):
        if scenario_id and scenario.get("followups"):
            followups = [str(item) for item in scenario.get("followups", [])]
            if followups:
                return followups[min(patient_turns, len(followups) - 1)]
        return "Okay, I understand."

    return reply_text


def _first_turn_reply(
    *,
    scenario: dict[str, Any],
    transcript: list[dict[str, str]],
    office_speech: str,
    call_memory: dict[str, Any] | None = None,
) -> Reply | None:
    if len(transcript) > 1:
        return None

    starter = str(scenario.get("starter", "")).strip()
    profile = (call_memory or {}).get("patient_profile", {}) if call_memory else {}
    first_name = str(profile.get("first_name", "")).strip()
    if starter:
        return Reply(text=starter)
    if first_name:
        return Reply(text=f"Yes, this is {first_name}.")
    return None


def _normalize_question(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "can",
        "could",
        "do",
        "for",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "that",
        "the",
        "there",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
        "you",
        "your",
    }
    return tuple(token for token in tokens if token not in stopwords)


def _repetition_detected(transcript: list[dict[str, str]]) -> bool:
    office_turns = [turn.get("text", "") for turn in transcript if turn.get("speaker") == "office"]
    if len(office_turns) < 2:
        return False
    recent = [_normalize_question(text) for text in office_turns[-2:]]
    if any(not tokens for tokens in recent):
        return False
    if recent[0] == recent[1]:
        return True
    if len(office_turns) >= 3:
        recent_three = [_normalize_question(text) for text in office_turns[-3:]]
        counts = Counter(recent_three)
        return any(count >= 2 for count in counts.values())
    return False


@dataclass
class Reply:
    text: str
    should_hangup: bool = False


class ReplyEngine:
    def initial_reply(
        self,
        *,
        scenario: dict[str, Any],
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        raise NotImplementedError

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        raise NotImplementedError


class RuleBasedReplyEngine(ReplyEngine):
    def initial_reply(
        self,
        *,
        scenario: dict[str, Any],
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        return Reply(text=str(scenario["starter"]))

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        guardrail_reply = _guardrail_reply(
            transcript=transcript,
            office_speech=office_speech,
            call_memory=call_memory,
        )
        if guardrail_reply is not None:
            return guardrail_reply

        first_turn = _first_turn_reply(
            scenario=scenario,
            transcript=transcript,
            office_speech=office_speech,
            call_memory=call_memory,
        )
        if first_turn is not None:
            return first_turn

        office_turns = [turn for turn in transcript if turn.get("speaker") == "office"]
        index = max(0, len(office_turns) - 1)
        followups = [str(item) for item in scenario.get("followups", [])]
        if followups:
            text = followups[min(index, len(followups) - 1)]
        else:
            text = "Okay, understood."

        if len(transcript) >= int(scenario.get("max_turns", 10)) * 2:
            return Reply(text="Thanks, I have what I need. Bye.", should_hangup=True)
        return Reply(text=text)


class OpenAICompatibleReplyEngine(ReplyEngine):
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        trace_dir: str | Path | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.trace_dir = Path(trace_dir) if trace_dir is not None else None
        self._trace_lock = threading.Lock()

    def _write_trace(self, payload: dict[str, Any]) -> None:
        if self.trace_dir is None:
            return
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.trace_dir / "llm-trace.jsonl"
        line = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        with self._trace_lock:
            with trace_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def initial_reply(
        self,
        *,
        scenario: dict[str, Any],
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        return Reply(text=str(scenario["starter"]))

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
        call_memory: dict[str, Any] | None = None,
    ) -> Reply:
        guardrail_reply = _guardrail_reply(
            transcript=transcript,
            office_speech=office_speech,
            call_memory=call_memory,
        )
        if guardrail_reply is not None:
            return guardrail_reply

        first_turn = _first_turn_reply(
            scenario=scenario,
            transcript=transcript,
            office_speech=office_speech,
            call_memory=call_memory,
        )
        if first_turn is not None:
            return first_turn

        messages = [
            {
                "role": "system",
                "content": build_patient_prompt(
                    objective=str(scenario["objective"]),
                    starter=str(scenario["starter"]),
                    followups=[str(item) for item in scenario.get("followups", [])],
                    failure_modes=[str(item) for item in scenario.get("failure_modes", [])],
                    patient_profile={
                        str(key): str(value)
                        for key, value in dict(scenario.get("patient_profile", {}) or {}).items()
                    }
                    or None,
                    call_memory=call_memory,
                )
                + "\nKeep responses to 1-2 short sentences. Never mention you are an AI.\n",
            }
        ]

        # Convert the conversation into office/patient turns.
        for turn in transcript[-8:]:
            role = "assistant" if turn["speaker"] == "patient" else "user"
            messages.append({"role": role, "content": turn["text"]})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 64,
        }
        result = http_post_json(
            url=f"{self.api_base}/chat/completions",
            data=payload,
            bearer_token=self.api_key,
            timeout=self.timeout_seconds,
        )
        text = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not text:
            text = "Okay. Can you say that one more time?"
        raw_text = text
        text = _shape_model_reply(
            scenario=scenario,
            transcript=transcript,
            office_speech=office_speech,
            call_memory=call_memory,
            reply_text=text,
        )
        self._write_trace(
            {
                "model": self.model,
                "scenario_id": scenario.get("id"),
                "objective": scenario.get("objective"),
                "turn_count": len(transcript),
                "office_speech": office_speech,
                "raw_reply_text": raw_text,
                "reply_text": text,
                "temperature": payload["temperature"],
                "max_tokens": payload["max_tokens"],
                "call_memory": call_memory or {},
                "messages": messages,
            }
        )
        if len(transcript) >= int(scenario.get("max_turns", 10)) * 2:
            return Reply(text="Thanks, I have what I need. Bye.", should_hangup=True)
        return Reply(text=text)
