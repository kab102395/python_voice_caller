from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
LOCAL_BASE_URL = "http://localhost:8000"
LOCAL_DASHBOARD_URL = f"{LOCAL_BASE_URL}/dashboard"
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"


def read_env_lines(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing env file: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_base_url(path: Path, base_url: str) -> None:
    lines = read_env_lines(path)
    updated = False
    for index, line in enumerate(lines):
        if line.startswith("BASE_URL="):
            lines[index] = f"BASE_URL={base_url}"
            updated = True
            break
    if not updated:
        lines.append(f"BASE_URL={base_url}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def wait_for_http(url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return
        except Exception as exc:  # pragma: no cover - transient startup wait
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}") from last_error


def start_process(args: list[str]) -> subprocess.Popen[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        args,
        cwd=str(ROOT),
        stdout=None,
        stderr=None,
        creationflags=creationflags,
    )


def terminate_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        proc.kill()


def read_ngrok_public_url() -> str:
    with urllib.request.urlopen(NGROK_API_URL, timeout=2.0) as response:
        payload = response.read().decode("utf-8")

    data = json.loads(payload)
    for tunnel in data.get("tunnels", []):
        public_url = tunnel.get("public_url", "")
        if str(public_url).startswith("https://"):
            return str(public_url)
    raise RuntimeError("No https ngrok tunnel found")


def wait_for_ngrok_public_url(timeout_seconds: float = 10.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return read_ngrok_public_url()
        except Exception as exc:  # pragma: no cover - transient startup wait
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError("Timed out waiting for ngrok tunnel URL") from last_error


def main() -> int:
    uvicorn_proc: subprocess.Popen[str] | None = None
    ngrok_proc: subprocess.Popen[str] | None = None
    try:
        uvicorn_proc = start_process([sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"])
        wait_for_http(f"{LOCAL_BASE_URL}/health", timeout_seconds=10.0)

        ngrok_proc = start_process(["ngrok", "http", "8000"])
        wait_for_http(NGROK_API_URL, timeout_seconds=10.0)
        public_url = wait_for_ngrok_public_url(timeout_seconds=10.0)

        current_env = "\n".join(read_env_lines(ENV_PATH))
        if f"BASE_URL={public_url}" not in current_env:
            write_base_url(ENV_PATH, public_url)

        webbrowser.open(LOCAL_DASHBOARD_URL)
        print(f"Dashboard: {LOCAL_DASHBOARD_URL}")
        print(f"Public URL: {public_url}")
        print("Press Ctrl+C to shut down.")

        while True:
            if uvicorn_proc.poll() is not None:
                raise RuntimeError("uvicorn stopped unexpectedly")
            if ngrok_proc.poll() is not None:
                raise RuntimeError("ngrok stopped unexpectedly")
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        terminate_process(ngrok_proc)
        terminate_process(uvicorn_proc)
        print("Shut down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
