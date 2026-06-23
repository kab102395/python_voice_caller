# Python Voice Caller

This repo is the working scaffold for the Pretty Good AI voice challenge.

The current implementation is intentionally narrow:

- `call_runner.py` places an outbound Twilio call.
- `batch_runner.py` runs the full scenario set sequentially.
- `app.py` answers Twilio webhooks, validates signatures, and runs a turn-based voice loop.
- Twilio handles speech recognition and text-to-speech for the first pass.
- The bot response engine uses an OpenAI-compatible chat API when `LLM_API_KEY` is set, and falls back to a deterministic scenario runner otherwise.
- Every call writes a transcript JSON file, a readable `.txt` transcript, and app logs under `artifacts/`.

## Important safety guard

The call runner only allows this number:

`+18054398008`

Anything else is rejected in code.

## Files

- `app.py` - FastAPI server for Twilio webhooks
- `call_runner.py` - outbound call entrypoint
- `batch_runner.py` - sequential runner for all scenarios
- `clients.py` - Twilio REST helpers, webhook validation, and HTTP helpers
- `config.py` - environment validation
- `engine.py` - reply generation
- `scenarios.py` - scenario catalog and prompt builder
- `ARCHITECTURE.md` - design notes
- `artifacts/` - logs, transcripts, and recordings

## Environment variables

Required:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `BASE_URL`

Optional:

- `ALLOWED_TARGET_NUMBER` - defaults to `+18054398008`
- `LLM_API_KEY` - enables LLM-backed responses
- `LLM_API_BASE` - defaults to `https://api.openai.com/v1`
- `LLM_MODEL` - defaults to `gpt-4o-mini`
- `LLM_TIMEOUT_SECONDS` - defaults to `20`
- `TWILIO_VOICE` - defaults to `Polly.Matthew-Neural`
- `MAX_CALL_TURNS` - defaults to `10`
- `MAX_CALL_SECONDS` - defaults to `180`

## Setup

Install dependencies, then create a `.env` file from `.env.example`.

Important: `.env.example` is only the template. The app loads `.env`.

## Run the server

```powershell
uvicorn app:app --host 0.0.0.0 --port 8000
```

The webhook URLs in `BASE_URL` must point to a publicly reachable HTTPS tunnel for real calls.

For local development:

- run the app on `localhost`
- expose it with a tunnel such as ngrok or Cloudflare Tunnel
- set `BASE_URL` to the tunnel's public HTTPS URL

Example pattern:

```powershell
uvicorn app:app --host 0.0.0.0 --port 8000
ngrok http 8000
```

Then set `BASE_URL` to the HTTPS forwarding URL that ngrok prints.

Live calls are rejected if `BASE_URL` points at `localhost`, `127.0.0.1`, or `::1`.

## Start a call

Dry run:

```powershell
python call_runner.py --scenario scheduling --dry-run
```

Live call:

```powershell
python call_runner.py --scenario scheduling
```

Run the full scenario batch:

```powershell
python batch_runner.py --dry-run
```

## Output

The app writes these artifacts:

- `artifacts/transcripts/<started_at>_<scenario>_<call_sid>.json`
- `artifacts/transcripts/<started_at>_<scenario>_<call_sid>.txt`
- `artifacts/recordings/<started_at>_<scenario>_<call_sid>_<recording_sid>.mp3`
- `artifacts/logs/app-<run_timestamp>.log`

## Runtime behavior

The bot opens with a scenario-specific patient line. Twilio's speech result is posted back to `/voice`, the reply engine generates the next patient turn, and the server returns the next TwiML response. The call ends when the engine decides the conversation is complete, the maximum turn count is reached, or the call is silent too long.

## What is secured

- Twilio webhook signatures are validated on every webhook.
- The call runner refuses any destination except the challenge number.
- Recording downloads use Twilio account auth, not public unauthenticated fetches.
- Session artifacts are written atomically to avoid partial files.
