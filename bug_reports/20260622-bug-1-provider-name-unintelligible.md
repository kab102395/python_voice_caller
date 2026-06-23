# Bug 1 — Provider name consistently unintelligible via TTS/STT

Severity: High  
Status: Open  
Scenarios: scheduling, reschedule, cancel

## Summary

The provider name is not stable across calls. The spoken name is transcribed differently on nearly every utterance, which makes it hard for a caller to understand who the appointment is with.

Observed variants from recent calls:

- "Z big new lucoski"
- "Z dig new Lakosky"
- "c big new lucosky"
- "Z big new lucasi"
- "Z big, new lucasi"

## Evidence

Recent transcript logs show the name varying across multiple calls and turns, even when the underlying appointment reference is the same. This appears in the `scheduling`, `reschedule`, and `cancel` scenarios.

## Impact

A real patient would not be able to reliably confirm the provider name. This reduces trust in the interaction and makes the flow feel unstable or unprofessional.

## Likely cause

The provider name is difficult for the TTS/STT chain to render consistently. The issue is likely in the telephony/text-to-speech/speech-to-text stack rather than the local orchestration code.

## Recommended follow-up

- Use a simpler placeholder provider name for the demo.
- Or spell the provider name phonetically in the prompt or confirmation text.
- Or avoid requiring the name to be spoken repeatedly and instead present it in a text confirmation.
