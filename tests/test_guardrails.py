from __future__ import annotations

import importlib
import asyncio
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
        cls.scenarios = importlib.import_module("scenarios")

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
        call_service = importlib.import_module("call_service")
        call_runner = importlib.import_module("call_runner")
        with patch.object(call_service, "create_twilio_call") as create_call:
            create_call.return_value = type("R", (), {"sid": "CA1", "status": "queued"})()
            with redirect_stdout(StringIO()):
                call_runner.start_call(
                    call_service.CallRequest(
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
            "id": "scheduling",
            "starter": "Hi, I need to set up an appointment for next week.",
            "followups": ["That is the only time I am free."],
            "failure_modes": [],
            "max_turns": 10,
        }
        opening = engine.initial_reply(scenario=scenario)
        self.assertTrue(opening.text)
        next_reply = engine.next_reply(
            scenario=scenario,
            transcript=[{"speaker": "office", "text": "What day works best?"}],
            office_speech="What day works best?",
        )
        self.assertTrue(next_reply.text)

    def test_repetition_guard_breaks_loops(self) -> None:
        engine = self.engine.RuleBasedReplyEngine()
        scenario = {
            "id": "scheduling",
            "starter": "Hi, I need to set up an appointment for next week.",
            "followups": [],
            "failure_modes": [],
            "max_turns": 10,
        }
        reply = engine.next_reply(
            scenario=scenario,
            transcript=[
                {"speaker": "office", "text": "What day works best?"},
                {"speaker": "patient", "text": "Friday afternoon works."},
                {"speaker": "office", "text": "What day works best?"},
            ],
            office_speech="What day works best?",
        )
        self.assertIn("already covered", reply.text.lower())

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

    def test_call_memory_tracks_recent_turns(self) -> None:
        scenario = self.app.scenario_context("refill")
        memory = self.app.CallMemory.from_scenario(scenario)
        memory.record_turn(speaker="office", text="What medication do you need refilled?")
        memory.record_turn(speaker="patient", text="I need Lisinopril 10mg.")
        self.assertEqual(memory.phase, "patient_turn")
        self.assertEqual(memory.last_office_question, "What medication do you need refilled?")
        self.assertIn("What medication do you need refilled?", memory.recent_office_questions)
        self.assertIn("I need Lisinopril 10mg.", memory.recent_patient_answers)
        self.assertEqual(memory.confirmed_facts.get("current_medication"), "Lisinopril 10mg")

    def test_prompt_builder_includes_call_memory(self) -> None:
        scenario = self.app.scenario_context("insurance")
        memory = self.app.CallMemory.from_scenario(scenario).to_dict()
        memory["confirmed_facts"] = {"insurance": "Blue Cross PPO"}
        prompt = self.scenarios.build_patient_prompt(
            objective="Ask an insurance coverage question.",
            starter="Do you take my insurance?",
            followups=["I'm on an employer plan."],
            failure_modes=["makes an unsupported coverage claim"],
            patient_profile=self.scenarios.DEFAULT_PATIENT_PROFILE,
            call_memory=memory,
        )
        self.assertIn("CALL MEMORY", prompt)
        self.assertIn("Blue Cross PPO", prompt)
        self.assertIn("REQUIRED FACTS FOR THIS SCENARIO", prompt)

    def test_prompt_builder_merges_default_and_scenario_profile(self) -> None:
        prompt = self.scenarios.build_patient_prompt(
            objective="Book a routine appointment for next week.",
            starter="Hi, I need to set up an appointment for next week.",
            followups=["Actually, do you have anything Friday afternoon?"],
            failure_modes=["forgets to ask for necessary scheduling details"],
            patient_profile={"visit_reason": "routine follow-up appointment"},
            call_memory=None,
        )
        self.assertIn("Phone: +1 (320) 381-0451", prompt)
        self.assertIn("Visit Reason: routine follow-up appointment", prompt)

    def test_call_event_hub_buffers_events(self) -> None:
        session = self.app.CallSession(
            call_sid="CAevent",
            scenario_id="scheduling",
            to_number="+18054398008",
            from_number="+15551234567",
            call_memory=self.app.CallMemory.from_scenario(self.app.scenario_context("scheduling")),
            started_at="2026-06-22T00:00:00Z",
            updated_at="2026-06-22T00:00:01Z",
        )
        event = self.app.publish_call_event(
            session,
            "transcript_line",
            {"speaker": "office", "text": "Hello there"},
        )
        backlog = self.app.call_event_hub.snapshot(session.call_sid)
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0]["event_type"], "transcript_line")
        self.assertEqual(event["speaker"], "office")
        self.assertEqual(backlog[0]["text"], "Hello there")

    def test_dashboard_api_lists_calls_from_transcripts(self) -> None:
        with TemporaryDirectory() as tmp:
            transcript_root = Path(tmp)
            with patch.object(self.app, "TRANSCRIPT_ROOT", transcript_root):
                session = self.app.CallSession(
                    call_sid="CA-api-1",
                    scenario_id="scheduling",
                    to_number="+18054398008",
                    from_number="+15551234567",
                    call_memory=self.app.CallMemory.from_scenario(self.app.scenario_context("scheduling")),
                    started_at="2026-06-22T00:00:00Z",
                    updated_at="2026-06-22T00:00:01Z",
                )
                session.add_turn(speaker="office", text="Hello", raw={})
                session.save()
                items = self.app.transcript_index()
                self.assertEqual(items[0]["call_sid"], "CA-api-1")
                self.assertNotIn("turns", items[0])
                filtered = self.app.transcript_index(scenario_id="scheduling", limit=1)
                self.assertEqual(len(filtered), 1)
                detail = self.app.resolve_call_record("CA-api-1")
                self.assertEqual(detail["call_sid"], "CA-api-1")
                transcript = asyncio.run(self.app.api_call_transcript("CA-api-1"))
                self.assertEqual(transcript["turns"][0]["text"], "Hello")

    def test_api_calls_rejects_invalid_limit(self) -> None:
        with self.assertRaises(self.app.HTTPException):
            asyncio.run(self.app.api_calls(limit=0))

    def test_dashboard_api_exposes_scenarios(self) -> None:
        response = asyncio.run(self.app.api_scenarios())
        items = response["items"]
        self.assertIn("scheduling", {item["id"] for item in items})

    def test_hard_edgecase_scenarios_present(self) -> None:
        expected = {
            "scheduling",
            "reschedule",
            "cancel",
            "refill",
            "controlled_refill",
            "identity_wrong_dob_persistent",
            "scheduling_impossible_constraint",
            "scheduling_pivot_mid_flow",
            "insurance",
            "escalation_demands_human",
        }
        self.assertTrue(expected.issubset(set(self.scenarios.SCENARIOS.keys())))

    def test_scenario_context_merges_profile_override(self) -> None:
        insurance = self.app.scenario_context("insurance")
        refill = self.app.scenario_context("refill")
        self.assertEqual(insurance["patient_profile"]["insurance"], "Blue Cross PPO")
        self.assertEqual(refill["patient_profile"]["preferred_pharmacy"], "Walgreens on Main Street")

    def test_api_bugs_parses_frontmatter(self) -> None:
        bugs = self.app.bug_index()
        self.assertGreaterEqual(len(bugs), 18)
        self.assertEqual(bugs[0]["id"], 1)
        self.assertIn("Provider name", bugs[0]["title"])

    def test_api_live_logs_reads_current_file(self) -> None:
        with TemporaryDirectory() as tmp:
            log_root = Path(tmp)
            log_path = log_root / "app.log"
            log_path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")
            with patch.object(self.app, "LIVE_LOG_SOURCES", {"app": log_path}):
                payload = asyncio.run(self.app.api_live_logs(source="app", limit=2))
                lines = [item["line"] for item in payload["items"]]
                self.assertEqual(lines, ["line-2", "line-3"])

    def test_api_call_start_uses_shared_service(self) -> None:
        with patch.object(self.app, "start_call") as start_call:
            start_call.return_value = {"sid": "CA1", "status": "queued"}
            result = asyncio.run(self.app.api_call_start({"scenario": "scheduling"}))
            self.assertEqual(result["sid"], "CA1")
            self.assertEqual(start_call.call_args.kwargs["emit_output"], False)

    def test_prompt_reply_disables_llm_after_quota_error(self) -> None:
        class FailingEngine:
            def initial_reply(self, *, scenario, call_memory=None):  # type: ignore[no-untyped-def]
                raise RuntimeError("HTTP 429 from upstream")

            def next_reply(self, *, scenario, transcript, office_speech, call_memory=None):  # type: ignore[no-untyped-def]
                raise RuntimeError("HTTP 429 from upstream")

        session = self.app.CallSession(
            call_sid="CA999",
            scenario_id="scheduling",
            to_number="+18054398008",
            from_number="+15551234567",
            call_memory=self.app.CallMemory.from_scenario(self.app.scenario_context("scheduling")),
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
            call_memory=self.app.CallMemory.from_scenario(self.app.scenario_context("scheduling")),
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
                    call_memory=self.app.CallMemory.from_scenario(self.app.scenario_context("scheduling")),
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
