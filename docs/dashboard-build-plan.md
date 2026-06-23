# Dashboard + Launcher — Build Plan

## Architecture Overview

```
launcher.py          ← single entry point
    │
    ├── starts uvicorn (app.py) as subprocess
    ├── starts ngrok, reads tunnel URL, patches .env BASE_URL
    ├── opens browser to http://localhost:8000/dashboard
    └── handles Ctrl+C shutdown of both processes

app.py (existing)
    ├── /dashboard       ← serves static HTML (new)
    ├── /api/call        ← new POST endpoint to trigger a call
    ├── /api/scenarios   ← already exists
    ├── /api/calls       ← already exists
    ├── /events/{sid}    ← already exists (SSE)
    └── /api/bugs        ← new endpoint, reads bug_reports/*.md

dashboard/
    └── index.html       ← single file, vanilla JS, no build step
```

---

## Phase A — Backend additions to `app.py`

### A1. `POST /api/call` — trigger a call from the dashboard

Add this endpoint. It accepts `{"scenario": "scheduling"}` and internally does exactly what
`call_runner.py` does — no subprocess, direct function call.

```python
@app.post("/api/call")
async def api_start_call(body: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(body.get("scenario", "scheduling"))
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario_id}")
    # call start_call() from call_runner imported directly
    # return {"sid": ..., "scenario": ..., "status": ...}
```

Import `start_call` and `CallRequest` from `call_runner`. Do **not** shell out — calling it
directly is cleaner and avoids env issues.

### A2. `GET /api/bugs` — serve bug index from markdown files

Parse `bug_reports/*.md` (exclude `INDEX.md`). Each file has frontmatter (`---` delimited).
Extract `id`, `title`, `severity`, `scenario`, `call_sid`, `date`. Return as JSON array sorted
by id.

```python
@app.get("/api/bugs")
async def api_bugs() -> dict[str, Any]:
    # glob bug_reports/*.md, skip INDEX.md
    # parse frontmatter between first two --- delimiters
    # return {"items": [...]}
```

No external YAML parser needed — the frontmatter is simple `key: value` lines, a 10-line
regex parse is sufficient.

### A3. `GET /dashboard` — serve the HTML file

```python
from fastapi.responses import FileResponse

@app.get("/dashboard")
async def dashboard() -> FileResponse:
    return FileResponse("dashboard/index.html")
```

---

## Phase B — `dashboard/index.html`

Single file. Vanilla JS. No React, no build step, no CDN fonts. Use CSS variables so it
looks clean. Four panels:

### Layout

```
┌─────────────────────────────────────────────────────┐
│  HEADER: server status · ngrok URL · engine type    │
├──────────────┬──────────────────────────────────────┤
│  LEFT PANEL  │  RIGHT PANEL                         │
│              │                                       │
│  Scenario    │  Live Call                            │
│  Picker      │  ─────────────────────────────────── │
│              │  [scenario badge] [elapsed timer]     │
│  [dropdown]  │                                       │
│  [CALL btn]  │  Transcript stream                    │
│              │  (turns appear here, color-coded)     │
│  Call        │                                       │
│  History     │  Call Memory                          │
│  ─────────── │  (confirmed facts, phase, turn count) │
│  (list of    │                                       │
│   past calls)│                                       │
│  (click →    ├──────────────────────────────────────┤
│   loads it)  │  Bug Reports                          │
│              │  (table: id · severity · scenario ·   │
│              │   title — from /api/bugs)             │
└──────────────┴──────────────────────────────────────┘
```

### JS Logic — five distinct modules

Write these as plain functions, not classes.

#### 1. `fetchScenarios()`

- On page load, `GET /api/scenarios`
- Populate the dropdown with `id` values
- Show `objective` text below dropdown when selection changes

#### 2. `startCall(scenarioId)`

- `POST /api/call` with `{"scenario": scenarioId}`
- On success, store returned `call_sid`
- Call `connectSSE(call_sid)` immediately

#### 3. `connectSSE(callSid)`

- Open `EventSource("/events/{callSid}")`
- On `transcript_line` event: append a turn bubble to the live panel, color by `speaker`
  (office = gray left, patient = blue right)
- On `call_completed` event: show completion banner, stop elapsed timer, close EventSource
- On `recording_ready` event: show recording path as a note
- On `session_started` event: clear transcript panel, reset timer

#### 4. `loadCallHistory()`

- On page load and after every call completes, `GET /api/calls?limit=20`
- Render as a clickable list: `[scenario] [turn_count turns] [status] [date]`
- Click → `GET /api/calls/{call_sid}` → render full transcript in right panel (replaces live view)

#### 5. `loadBugs()`

- On page load, `GET /api/bugs`
- Render as a table with severity color coding: High = red, Medium = yellow, Low = gray
- Each row: id · severity chip · scenario · title

### SSE Event Types to Handle

| Event | Action |
|---|---|
| `transcript_line` | Append bubble — speaker, text, confidence if present |
| `call_completed` | Show reason banner, stop timer |
| `recording_ready` | Append recording path note |
| `session_started` | Clear panel, show scenario name |
| `call_status` | Update status badge in header |

---

## Phase C — `launcher.py`

Single file. Starts everything in the right order. Clean shutdown on Ctrl+C.

### Startup Sequence

```
1.  Load .env to get current BASE_URL
2.  Start uvicorn as subprocess (subprocess.Popen)
3.  Poll GET http://localhost:8000/health until 200 (max 10s, 0.5s intervals)
4.  Start ngrok via subprocess: ngrok http 8000 --log=stdout
5.  Read ngrok local API: GET http://localhost:4040/api/tunnels
6.  Extract the https tunnel URL
7.  If BASE_URL in .env differs from ngrok URL → rewrite .env with new BASE_URL
      (targeted line replacement — do not clobber other keys)
8.  Open browser: webbrowser.open("http://localhost:8000/dashboard")
9.  Print: "Dashboard: http://localhost:8000/dashboard"
10. Print: "Public URL: {ngrok_url}"
11. Block waiting for Ctrl+C
```

### Shutdown (signal handler or try/finally)

```
1. Terminate ngrok subprocess
2. Terminate uvicorn subprocess
3. Print "Shut down."
```

### .env Rewrite Rule

Read the file line by line. Find the line starting with `BASE_URL=`. Replace it. Write the
file back. Never parse or regenerate the whole file — only touch that one line.

---

## Phase D — Polish

These are small but make the Loom look sharp:

- **Elapsed timer** — JS `setInterval` counting up from call start, stops on `call_completed`
- **Severity chips** — inline `<span>` with background color, no images
- **Auto-scroll** — transcript panel scrolls to bottom on each new turn
- **Scenario objective text** — show `objective` below the dropdown when scenario is selected
- **Empty states** — "No calls yet" / "No bugs loaded" messages, not blank panels
- **Call Memory sidebar** — after each `transcript_line`, re-fetch `/api/calls/{call_sid}`
  for updated `call_memory.confirmed_facts` and render them as a small key-value list

---

## File Checklist

```
dashboard/
  index.html          ← Phase B (new)

app.py                ← Phase A: add /api/call, /api/bugs, /dashboard routes

launcher.py           ← Phase C (new)
```

Three files. Everything else already exists and does not need to change.

---

## Order of Work

| Step | Task | Why first |
|---|---|---|
| 1 | `GET /api/bugs` in `app.py` | Isolated, no dependencies, test with curl |
| 2 | `POST /api/call` in `app.py` | Import `start_call`, test with curl |
| 3 | `GET /dashboard` route in `app.py` | One line, unblocks HTML work |
| 4 | `dashboard/index.html` | Build panel by panel, verify each API route as wired |
| 5 | `launcher.py` | Last — app must be confirmed working manually first |
