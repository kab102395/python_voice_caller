from __future__ import annotations

import importlib
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class GuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC1234567890abcdef1234567890abcdef")
        os.environ.setdefault("TWILIO_AUTH_TOKEN", "token123")
        os.environ.setdefault("TWILIO_PHONE_NUMBER", "+15551234567")
        os.environ.setdefault("BASE_URL", "https://example.com")
        os.environ.setdefault("ALLOWED_TARGET_NUMBER", "+18054398008")
        cls.app = importlib.import_module("app")
        cls.engine = importlib.import_module("engine")

    def test_target_number_allowlist(self) -> None:
        self.app.sanitized_target_number("+18054398008")
        with self.assertRaises(RuntimeError):
            self.app.sanitized_target_number("+15550001111")

    def test_call_runner_rejects_from_number_override(self) -> None:
        call_runner = importlib.import_module("call_runner")
        with patch("sys.argv", ["call_runner.py", "--from-number", "+15550001111"]):
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    call_runner.parse_args()

    def test_call_runner_uses_configured_from_number(self) -> None:
        call_runner = importlib.import_module("call_runner")
        with patch.object(call_runner, "create_twilio_call") as create_call:
            create_call.return_value = type("R", (), {"sid": "CA1", "status": "queued"})()
            with redirect_stdout(StringIO()):
                call_runner.start_call(
                    call_runner.CallRequest(
                        scenario="scheduling",
                        target_number="+18054398008",
                        dry_run=False,
                    )
                )
            kwargs = create_call.call_args.kwargs
            self.assertEqual(kwargs["from_number"], "+15551234567")
            self.assertEqual(kwargs["to_number"], "+18054398008")

    def test_clean_text_normalizes_and_truncates(self) -> None:
        self.assertEqual(self.app.clean_text("  hello   there  "), "hello there")
        self.assertTrue(len(self.app.clean_text("x" * 800)) <= 400)

    def test_rule_based_engine_progresses(self) -> None:
        engine = self.engine.RuleBasedReplyEngine()
        scenario = {
            "id": "weekend_trap",
            "starter": "Can I come in Sunday at 10am?",
            "followups": ["That is the only time I am free."],
            "failure_modes": [],
            "max_turns": 10,
        }
        opening = engine.initial_reply(scenario=scenario)
        self.assertIn("Sunday", opening.text)
        next_reply = engine.next_reply(
            scenario=scenario,
            transcript=[{"speaker": "office", "text": "We are closed on Sundays."}],
            office_speech="We are closed on Sundays.",
        )
        self.assertTrue(next_reply.text)

    def test_rule_based_engine_hangs_up_on_goodbye(self) -> None:
        engine = self.engine.RuleBasedReplyEngine()
        scenario = {
            "id": "cancel",
            "starter": "I need to cancel my appointment.",
            "followups": [],
            "failure_modes": [],
            "max_turns": 10,
        }
        reply = engine.next_reply(
            scenario=scenario,
            transcript=[{"speaker": "office", "text": "Thank you, goodbye."}],
            office_speech="Thank you, goodbye.",
        )
        self.assertTrue(reply.should_hangup)

    def test_prompt_reply_disables_llm_after_quota_error(self) -> None:
        class FailingEngine:
            def initial_reply(self, *, scenario):  # type: ignore[no-untyped-def]
                raise RuntimeError("HTTP 429 from upstream")

            def next_reply(self, *, scenario, transcript, office_speech):  # type: ignore[no-untyped-def]
                raise RuntimeError("HTTP 429 from upstream")

        session = self.app.CallSession(
            call_sid="CA999",
            scenario_id="scheduling",
            to_number="+18054398008",
            from_number="+15551234567",
            started_at="2026-06-22T00:00:00Z",
            updated_at="2026-06-22T00:00:01Z",
        )
        with patch.object(self.app, "get_engine", return_value=FailingEngine()):
            self.app._engine = None
            self.app._engine_disabled_reason = None
            reply = self.app.prompt_reply(session)
        self.assertIsInstance(reply, self.engine.Reply)
        self.assertEqual(self.app._engine_disabled_reason, "quota")
        self.assertIsInstance(self.app._engine, self.engine.RuleBasedReplyEngine)

    def test_should_force_hangup_by_elapsed_time(self) -> None:
        session = self.app.CallSession(
            call_sid="CA777",
            scenario_id="scheduling",
            to_number="+18054398008",
            from_number="+15551234567",
            started_at="2020-01-01T00:00:00Z",
            updated_at="2020-01-01T00:00:01Z",
        )
        force, reason = self.app.should_force_hangup(session)
        self.assertTrue(force)
        self.assertEqual(reason, "max_call_seconds_reached")

    def test_session_saves_text_transcript(self) -> None:
        with TemporaryDirectory() as tmp:
            transcript_root = Path(tmp)
            with patch.object(self.app, "TRANSCRIPT_ROOT", transcript_root):
                session = self.app.CallSession(
                    call_sid="CA123",
                    scenario_id="scheduling",
                    to_number="+18054398008",
                    from_number="+15551234567",
                    started_at="2026-06-22T00:00:00Z",
                    updated_at="2026-06-22T00:00:01Z",
                )
                session.add_turn(speaker="office", text="Hello", raw={})
                session.add_turn(speaker="patient", text="Hi", raw={})
                session.save()
                json_path = transcript_root / "20260622-000000_scheduling_CA123.json"
                txt_path = transcript_root / "20260622-000000_scheduling_CA123.txt"
                self.assertTrue(json_path.exists())
                self.assertTrue(txt_path.exists())
                txt = txt_path.read_text(encoding="utf-8")
                self.assertIn("turns:", txt)
                self.assertIn("OFFICE: Hello", txt)
                self.assertIn("PATIENT: Hi", txt)

    def test_batch_runner_enumerates_all_scenarios(self) -> None:
        batch_runner = importlib.import_module("batch_runner")
        self.assertEqual(
            batch_runner.iter_batch_scenarios(),
            list(batch_runner.SCENARIOS.keys()),
        )
        self.assertEqual(
            batch_runner.iter_batch_scenarios(limit=3),
            list(batch_runner.SCENARIOS.keys())[:3],
        )


if __name__ == "__main__":
    unittest.main()
