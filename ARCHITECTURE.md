# Architecture

## Overview

This project is a minimal outbound voice-call harness for the challenge. The implementation is optimized for reliability and security first: a narrow Twilio webhook loop, explicit destination allowlisting, webhook signature validation, and deterministic artifact writing.

The same call path can be driven one scenario at a time or by the sequential batch runner for faster evidence collection.

## Call flow

1. `call_runner.py` creates an outbound Twilio call to the approved number.
2. Twilio requests `/twiml` on `app.py`.
3. The server creates or resumes a per-call session and returns TwiML with a speech `Gather`.
4. Twilio converts the remote party's speech into a text result and posts it to `/voice`.
   The app also publishes per-turn transcript events to `/events/{call_sid}` for the dashboard.
5. The reply engine generates the next patient response.
6. The server returns the next TwiML turn, or hangs up if the call is done.
7. Twilio posts status and recording callbacks, and the server stores transcripts, readable transcript text, and recordings under `artifacts/`.
8. A read-only dashboard API exposes `/api/scenarios`, `/api/calls`, and `/api/calls/{call_sid}` using transcript files as the canonical data source.
9. The dashboard UI is served from `/dashboard`, and `launcher.py` starts the app plus ngrok for local use.

## Why this design

- Twilio-native speech turns avoid the complexity and fragility of a custom streaming audio stack for the first pass.
- Webhook signature validation protects the public endpoints from spoofed requests.
- The number allowlist prevents accidental misuse.
- Atomic transcript writes avoid corrupt artifacts if the process is interrupted.
- The human-readable transcript export is written from the structured call session so the `.json` and `.txt` files stay in sync.
- The reply engine is pluggable: use the OpenAI-compatible client when an API key is present, otherwise fall back to a deterministic scenario runner.

## Tradeoffs

This design is simpler than a raw media-stream + custom STT/TTS stack. That is deliberate. It gets a real end-to-end call path working quickly, keeps the server easier to reason about, and provides a safe base for upgrading to a richer audio pipeline later if the challenge requires it.
