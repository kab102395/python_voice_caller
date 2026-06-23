from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
import shutil
import textwrap
from pathlib import Path

from batch_runner import build_requests as build_batch_requests
from config import get_settings
from launcher import (
    ENV_PATH,
    LOCAL_BASE_URL,
    LOCAL_DASHBOARD_URL,
    NGROK_API_URL,
    ngrok_public_url_if_available,
    read_env_lines,
    start_process,
    terminate_process,
    wait_for_http,
    wait_for_ngrok_public_url,
    write_base_url,
)


ROOT = Path(__file__).resolve().parent
LOCAL_RECORDING_ROOT = ROOT / "artifacts" / "recordings"
LOCAL_TRANSCRIPT_ROOT = ROOT / "artifacts" / "transcripts"
LOG_ROOT = ROOT / "artifacts" / "logs"


def fetch_json(url: str, *, method: str = "GET", body: dict[str, object] | None = None) -> dict[str, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=8.0) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the app in an interactive terminal menu.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Print a lightweight status summary after launch, then enter the menu.",
    )
    return parser.parse_args()


def ensure_stack() -> tuple[str, subprocess.Popen[str] | None, subprocess.Popen[str] | None]:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    uvicorn_log = open(LOG_ROOT / "launcher-uvicorn.log", "a", encoding="utf-8")
    ngrok_log = open(LOG_ROOT / "launcher-ngrok.log", "a", encoding="utf-8")
    uvicorn_proc: subprocess.Popen[str] | None = None
    ngrok_proc: subprocess.Popen[str] | None = None

    if not _health_ok():
        uvicorn_proc = start_process(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=uvicorn_log,
            stderr=uvicorn_log,
        )
        wait_for_http(f"{LOCAL_BASE_URL}/health", timeout_seconds=10.0)

    public_url = ngrok_public_url_if_available()
    if not public_url:
        ngrok_proc = start_process(["ngrok", "http", "8000"], stdout=ngrok_log, stderr=ngrok_log)
        wait_for_http(NGROK_API_URL, timeout_seconds=10.0)
        public_url = wait_for_ngrok_public_url(timeout_seconds=10.0)

    current_env = "\n".join(read_env_lines(ENV_PATH))
    if f"BASE_URL={public_url}" not in current_env:
        write_base_url(ENV_PATH, public_url)
    return public_url, uvicorn_proc, ngrok_proc


def _health_ok() -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_BASE_URL}/health", timeout=1.0) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def print_header(public_url: str) -> None:
    root = fetch_json(f"{LOCAL_BASE_URL}/")
    scenarios = fetch_json(f"{LOCAL_BASE_URL}/api/scenarios").get("items", [])
    bugs = fetch_json(f"{LOCAL_BASE_URL}/api/bugs").get("items", [])
    calls = fetch_json(f"{LOCAL_BASE_URL}/api/calls?limit=5").get("items", [])
    print("\n=== Pretty Good AI CLI ===")
    print(f"Local dashboard: {LOCAL_DASHBOARD_URL}")
    print(f"Public URL: {public_url}")
    print(f"Engine: {root.get('engine', '-')}")
    print(f"Base URL: {root.get('base_url', '-')}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Bugs: {len(bugs)}")
    print("Recent calls:")
    for item in calls[:5]:
        print(f"  - {item.get('scenario_id', '-'):>28} | {item.get('status', '-'):<10} | {item.get('call_sid', '-')}")


def list_scenarios() -> list[dict[str, object]]:
    return list(fetch_json(f"{LOCAL_BASE_URL}/api/scenarios").get("items", []))


def list_calls(limit: int = 10) -> list[dict[str, object]]:
    return list(fetch_json(f"{LOCAL_BASE_URL}/api/calls?limit={limit}").get("items", []))


def list_bugs() -> list[dict[str, object]]:
    return list(fetch_json(f"{LOCAL_BASE_URL}/api/bugs").get("items", []))


def start_call(scenario_id: str, *, dry_run: bool = False) -> dict[str, object]:
    return fetch_json(f"{LOCAL_BASE_URL}/api/call", method="POST", body={"scenario": scenario_id, "dry_run": dry_run})


def load_call(call_sid: str) -> dict[str, object]:
    return fetch_json(f"{LOCAL_BASE_URL}/api/calls/{urllib.parse.quote(call_sid, safe='')}")


def load_transcript(call_sid: str) -> dict[str, object]:
    return fetch_json(f"{LOCAL_BASE_URL}/api/calls/{urllib.parse.quote(call_sid, safe='')}/transcript")


def stop_call(call_sid: str) -> dict[str, object]:
    return fetch_json(
        f"{LOCAL_BASE_URL}/api/calls/{urllib.parse.quote(call_sid, safe='')}/stop",
        method="POST",
        body={"reason": "killed_from_cli"},
    )


def open_path(path: str) -> bool:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    if not candidate.exists():
        print(f"Missing file: {candidate}")
        return False
    try:
        os.startfile(candidate)  # type: ignore[attr-defined]
        return True
    except AttributeError:
        subprocess.Popen(["cmd", "/c", "start", "", str(candidate)], shell=False)
        return True


def print_scenarios() -> None:
    scenarios = list_scenarios()
    print("\nScenarios:")
    for index, scenario in enumerate(scenarios, start=1):
        required = ", ".join(scenario.get("required_facts", []) or []) or "none"
        print(f"  {index:>2}. {scenario.get('id', '-')} | required: {required}")


def print_calls(limit: int = 10) -> None:
    calls = list_calls(limit=limit)
    print("\nRecent calls:")
    for index, item in enumerate(calls, start=1):
        print(
            f"  {index:>2}. {item.get('scenario_id', '-'):>28} | "
            f"{item.get('status', '-'):<10} | {item.get('turn_count', 0):>2} turns | "
            f"{item.get('call_sid', '-')}"
        )


def active_calls(limit: int = 20) -> list[dict[str, object]]:
    calls = list_calls(limit=limit)
    return [item for item in calls if str(item.get("status", "")).lower() != "completed"]


def print_bugs() -> None:
    bugs = list_bugs()
    print("\nBugs:")
    for item in bugs[:20]:
        print(
            f"  #{item.get('id', '-'):<2} [{item.get('severity', '-')}] "
            f"{item.get('scenario', '-')} - {item.get('title', '-')}"
        )


def choose_index(prompt: str, max_index: int) -> int | None:
    value = input(prompt).strip()
    if not value:
        return None
    try:
        index = int(value)
    except ValueError:
        print("Enter a number.")
        return None
    if index < 1 or index > max_index:
        print(f"Choose a value between 1 and {max_index}.")
        return None
    return index


def run_single_call() -> None:
    scenarios = list_scenarios()
    print_scenarios()
    index = choose_index("Select a scenario number: ", len(scenarios))
    if index is None:
        return
    scenario_id = str(scenarios[index - 1].get("id", ""))
    result = start_call(scenario_id)
    print(json.dumps(result, indent=2))


def run_batch() -> None:
    scenarios = list_scenarios()
    limit_value = input(f"How many scenarios? [1-{len(scenarios)} or blank for all]: ").strip()
    if limit_value:
        try:
            limit = max(1, min(len(scenarios), int(limit_value)))
        except ValueError:
            print("Invalid number.")
            return
    else:
        limit = len(scenarios)
    dry_run = input("Dry run only? [y/N]: ").strip().lower().startswith("y")
    requests = build_batch_requests(dry_run=dry_run, limit=limit)
    for index, request in enumerate(requests, start=1):
        print(f"\n[{index}/{len(requests)}] {request.scenario}")
        print(json.dumps(start_call(request.scenario, dry_run=dry_run), indent=2))


def pick_call_sid(*, live_only: bool = False) -> str | None:
    calls = active_calls(limit=20) if live_only else list_calls(limit=10)
    if not calls:
        print("No calls available.")
        return None
    print("\nCalls:")
    for index, item in enumerate(calls, start=1):
        print(
            f"  {index:>2}. {item.get('scenario_id', '-'):>28} | "
            f"{item.get('status', '-'):<10} | {item.get('turn_count', 0):>2} turns | "
            f"{item.get('call_sid', '-')}"
        )
    choice = input("Choose a number or paste a call SID: ").strip()
    if not choice:
        return None
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(calls):
            return str(calls[index - 1].get("call_sid", "")).strip()
        print(f"Choose a value between 1 and {len(calls)}.")
        return None
    return choice


def inspect_call() -> None:
    print_calls(limit=10)
    call_sid = input("Enter call SID: ").strip()
    if call_sid.isdigit():
        calls = list_calls(limit=10)
        index = int(call_sid)
        if 1 <= index <= len(calls):
            call_sid = str(calls[index - 1].get("call_sid", "")).strip()
    if not call_sid:
        return
    try:
        record = load_call(call_sid)
        transcript = load_transcript(call_sid)
    except Exception as exc:
        print(f"Unable to load call {call_sid}: {exc}")
        return
    print(json.dumps(record, indent=2))
    print("\nTranscript turns:")
    for turn in transcript.get("turns", []):
        print(f"  {turn.get('speaker', '-').upper()}: {turn.get('text', '')}")


def format_log_lines(lines: list[dict[str, object]]) -> list[str]:
    formatted: list[str] = []
    for item in lines:
        source = str(item.get("source", "log")).upper()
        line = str(item.get("line", "")).rstrip()
        if line:
            formatted.append(f"[{source}] {line}")
    return formatted


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def terminal_width() -> int:
    return max(80, shutil.get_terminal_size((120, 24)).columns)


def wrap_line(text: str, *, prefix: str = "", width: int | None = None) -> list[str]:
    width = width or terminal_width()
    usable_width = max(20, width - len(prefix))
    wrapped = textwrap.wrap(
        text,
        width=usable_width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if not wrapped:
        return [prefix.rstrip()]
    return [prefix + wrapped[0]] + [(" " * len(prefix)) + part for part in wrapped[1:]]


def print_section(title: str, lines: list[str], *, empty_message: str = "No data") -> None:
    width = terminal_width()
    title_text = f" {title} "
    line_width = max(0, width - len(title_text) - 2)
    print(f"\n{title_text}{'-' * line_width}")
    if not lines:
        print(f"  {empty_message}")
        return
    for line in lines:
        for wrapped in wrap_line(line, prefix="  ", width=width):
            print(wrapped)


def render_live_snapshot(record: dict[str, object], app_lines: list[str], uvicorn_lines: list[str], ngrok_lines: list[str]) -> None:
    clear_screen()
    width = terminal_width()
    scenario = str(record.get("scenario_id", "-"))
    call_sid = str(record.get("call_sid", "-"))
    status = str(record.get("status", "-"))
    turn_count = int(record.get("turn_count", 0) or 0)
    elapsed = record.get("elapsed_seconds")
    end_reason = str(record.get("end_reason") or "")

    print("Pretty Good AI live follow")
    print("=" * min(width, 80))
    print(f"Call SID : {call_sid}")
    print(f"Scenario : {scenario}")
    print(f"Status   : {status}")
    print(f"Turns    : {turn_count}")
    if elapsed is not None:
        print(f"Elapsed  : {elapsed}s")
    if end_reason:
        print(f"End reason: {end_reason}")
    print("Press Ctrl+C to stop following.")

    turns = record.get("turns", [])
    if isinstance(turns, list) and turns:
        print_section(
            "Transcript",
            [
                f"{str(turn.get('speaker', '-')).upper()}: {str(turn.get('text', '')).strip()}"
                for turn in turns[-8:]
                if str(turn.get("text", "")).strip()
            ],
            empty_message="Waiting for transcript turns...",
        )
    else:
        print_section("Transcript", [], empty_message="Waiting for transcript turns...")

    print_section("App log", app_lines[-12:])
    print_section("Uvicorn log", uvicorn_lines[-10:])
    print_section("ngrok log", ngrok_lines[-10:])


def follow_live_call() -> None:
    call_sid = pick_call_sid(live_only=True)
    if not call_sid:
        return
    last_snapshot: tuple[int, str, str, str, str, str] | None = None
    print(f"\nFollowing {call_sid}. Press Ctrl+C to stop.\n")
    try:
        while True:
            record = load_call(call_sid)
            app_lines = format_log_lines(list(fetch_json(f"{LOCAL_BASE_URL}/api/live-logs?source=app&limit=120").get("items", [])))
            uvicorn_lines = format_log_lines(list(fetch_json(f"{LOCAL_BASE_URL}/api/live-logs?source=uvicorn&limit=120").get("items", [])))
            ngrok_lines = format_log_lines(list(fetch_json(f"{LOCAL_BASE_URL}/api/live-logs?source=ngrok&limit=120").get("items", [])))

            current_snapshot = (
                int(record.get("turn_count", 0) or 0),
                str(record.get("status", "")),
                str(record.get("end_reason") or ""),
                app_lines[-1] if app_lines else "",
                uvicorn_lines[-1] if uvicorn_lines else "",
                ngrok_lines[-1] if ngrok_lines else "",
            )
            if current_snapshot != last_snapshot:
                render_live_snapshot(record, app_lines, uvicorn_lines, ngrok_lines)
                last_snapshot = current_snapshot

            status = str(record.get("status", "")).lower()
            if status == "completed":
                print(f"\nCall completed: {record.get('end_reason') or 'done'}")
                break
            time.sleep(1.25)
    except KeyboardInterrupt:
        print("\nStopped following live call.")


def kill_live_call() -> None:
    call_sid = pick_call_sid(live_only=True)
    if not call_sid:
        return
    confirm = input(f"Stop live call {call_sid}? Type YES to confirm: ").strip()
    if confirm != "YES":
        print("Cancelled.")
        return
    try:
        result = stop_call(call_sid)
    except Exception as exc:
        print(f"Unable to stop call {call_sid}: {exc}")
        return
    print(json.dumps(result, indent=2))


def open_artifact() -> None:
    call_sid = input("Enter call SID: ").strip()
    if call_sid.isdigit():
        calls = list_calls(limit=10)
        index = int(call_sid)
        if 1 <= index <= len(calls):
            call_sid = str(calls[index - 1].get("call_sid", "")).strip()
    if not call_sid:
        return
    try:
        record = load_call(call_sid)
        transcript = load_transcript(call_sid)
    except Exception as exc:
        print(f"Unable to load call {call_sid}: {exc}")
        return
    print("\n1) Open transcript JSON")
    print("2) Open transcript TXT")
    print("3) Open recording MP3")
    choice = input("Choose artifact: ").strip()
    if choice == "1" and transcript.get("transcript_json_path"):
        open_path(str(transcript["transcript_json_path"]))
    elif choice == "2" and transcript.get("transcript_text_path"):
        open_path(str(transcript["transcript_text_path"]))
    elif choice == "3" and record.get("recording_path"):
        open_path(str(record["recording_path"]))
    else:
        print("Nothing opened.")


def menu_loop(public_url: str) -> None:
    while True:
        print_header(public_url)
        print("\nMenu:")
        print("  1) List scenarios")
        print("  2) Start one call")
        print("  3) Run batch")
        print("  4) List recent calls")
        print("  5) Inspect a call")
        print("  6) List bugs")
        print("  7) Open transcript or recording")
        print("  8) Follow live call")
        print("  9) Stop live call")
        print(" 10) Open dashboard in browser")
        print(" 11) Refresh summary")
        print("  0) Quit")
        choice = input("\nChoice: ").strip()
        if choice == "1":
            print_scenarios()
        elif choice == "2":
            run_single_call()
        elif choice == "3":
            run_batch()
        elif choice == "4":
            print_calls(limit=10)
        elif choice == "5":
            inspect_call()
        elif choice == "6":
            print_bugs()
        elif choice == "7":
            open_artifact()
        elif choice == "8":
            follow_live_call()
        elif choice == "9":
            kill_live_call()
        elif choice == "10":
            webbrowser.open(LOCAL_DASHBOARD_URL)
        elif choice == "11":
            continue
        elif choice == "0":
            break
        else:
            print("Unknown choice.")
        input("\nPress Enter to continue...")


def main() -> int:
    args = parse_args()
    uvicorn_proc = None
    ngrok_proc = None
    try:
        public_url, uvicorn_proc, ngrok_proc = ensure_stack()
        if args.watch:
            print_header(public_url)
        menu_loop(public_url)
    except KeyboardInterrupt:
        pass
    finally:
        terminate_process(ngrok_proc)
        terminate_process(uvicorn_proc)
        print("Shut down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
