from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from collections import Counter

from clients import http_post_json
from scenarios import build_patient_prompt


GOODBYE_RE = re.compile(r"\b(bye|goodbye|see you|take care|have a good day|have a great day)\b", re.I)
WRAP_UP_RE = re.compile(r"\b(is there anything else|anything else I can help|anything else for you)\b", re.I)
CONFIRMATION_RE = re.compile(r"\b(is that correct|is this correct|is all (of )?that correct|does that (sound|look) right|is this the (appointment|one)|is that the (appointment|one))\b", re.I)
REPETITION_GUARD_REPLY = "I think we've already covered that. What would you like me to do next?"
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
        if _repetition_detected(transcript):
            return Reply(text=REPETITION_GUARD_REPLY)
        if CONFIRMATION_RE.search(office_speech):
            return Reply(text="Yes, that's correct.", should_hangup=False)
        if GOODBYE_RE.search(office_speech):
            return Reply(text="Thanks, that helps. Bye.", should_hangup=True)

        if WRAP_UP_RE.search(office_speech) and len(transcript) >= 6:
            return Reply(text="No, that's all I needed. Thanks, bye!", should_hangup=True)

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
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

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
        if _repetition_detected(transcript):
            return Reply(text=REPETITION_GUARD_REPLY)
        if CONFIRMATION_RE.search(office_speech):
            return Reply(text="Yes, that's correct.", should_hangup=False)
        if GOODBYE_RE.search(office_speech):
            return Reply(text="Thanks, that helps. Bye.", should_hangup=True)

        if WRAP_UP_RE.search(office_speech) and len(transcript) >= 6:
            return Reply(text="No, that's all I needed. Thanks, bye!", should_hangup=True)

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
        for turn in transcript[-12:]:
            role = "assistant" if turn["speaker"] == "patient" else "user"
            messages.append({"role": role, "content": turn["text"]})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 80,
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
        if len(transcript) >= int(scenario.get("max_turns", 10)) * 2:
            return Reply(text="Thanks, I have what I need. Bye.", should_hangup=True)
        return Reply(text=text)
