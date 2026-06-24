# Bug 1 — PGAI speech layer garbles medication names and greeting questions

Severity: Medium
Status: Open
Scenarios: refill, controlled_refill, reschedule

## What PGAI did wrong

The PGAI agent's speech-to-text pipeline garbles domain-specific medication names and standard greeting phrases. The garbled text is what the agent receives and acts on, producing incoherent responses or losing the question entirely.

## Evidence

**Refill call — transcript 20260623-192346_refill_CAb84a28.txt, turn 5:**

> PGAI: "Thanks, Alex. How many days of **life in a pearl**? Do you have left?"

The intended phrase was: "How many days of **Lisinopril** do you have left?" The medication name was completely lost. A real patient would have no idea what was being asked.

**Reschedule call — transcript 20260623-192213_reschedule_CA1fa6fd.txt, turn 1:**

> PGAI: "...thanks for calling Pivot Point Orthopedics part of pretty good AI **my speaking with Alex**"

The intended phrase was: "Am I speaking with Alex?" The question was garbled into a statement fragment, dropping the identity check.

**Earlier runs (controlled_refill and cancel scenarios):**

- "Adderall" rendered as "outer all" or "adderal"
- "Dr. Doogie Howser" rendered as "Dudy Howser" or "Doogie house"
- "Dr. Zbigniew Lukoski" rendered with varying pronunciations across turns

## Impact

A real patient receiving garbled medication names or broken greeting questions would be confused and might confirm incorrect information. The greeting garble means the identity verification question is never actually heard — the call proceeds with a broken trust gate at the very start.

## Root cause

PGAI's STT pipeline lacks custom vocabulary or phonetic handling for medical terminology and medication brand names. Greeting questions are also vulnerable to codec artifact on standard telephony, producing fragment transcriptions.

## Recommended fix

- Pre-load a custom STT vocabulary with medication names used in the system (Lisinopril, Adderall, etc.)
- Validate transcription confidence on medication-name tokens and re-prompt if confidence is below threshold
- Add a brief silence before the greeting question to allow the STT pipeline to synchronize with the audio stream
