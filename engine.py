from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from clients import http_post_json
from scenarios import build_patient_prompt


GOODBYE_RE = re.compile(r"\b(bye|goodbye|see you|take care|have a good day|have a great day)\b", re.I)
WRAP_UP_RE = re.compile(r"\b(is there anything else|anything else I can help|anything else for you)\b", re.I)


@dataclass
class Reply:
    text: str
    should_hangup: bool = False


class ReplyEngine:
    def initial_reply(self, *, scenario: dict[str, Any]) -> Reply:
        raise NotImplementedError

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
    ) -> Reply:
        raise NotImplementedError


class RuleBasedReplyEngine(ReplyEngine):
    def initial_reply(self, *, scenario: dict[str, Any]) -> Reply:
        return Reply(text=str(scenario["starter"]))

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
    ) -> Reply:
        if GOODBYE_RE.search(office_speech):
            return Reply(text="Thanks, that helps. Bye.", should_hangup=True)

        if WRAP_UP_RE.search(office_speech) and len(transcript) >= 6:
            return Reply(text="No, that's all I needed. Thanks, bye!", should_hangup=True)

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

    def initial_reply(self, *, scenario: dict[str, Any]) -> Reply:
        return Reply(text=str(scenario["starter"]))

    def next_reply(
        self,
        *,
        scenario: dict[str, Any],
        transcript: list[dict[str, str]],
        office_speech: str,
    ) -> Reply:
        if GOODBYE_RE.search(office_speech):
            return Reply(text="Thanks, that helps. Bye.", should_hangup=True)

        if WRAP_UP_RE.search(office_speech) and len(transcript) >= 6:
            return Reply(text="No, that's all I needed. Thanks, bye!", should_hangup=True)

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
