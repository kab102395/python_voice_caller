# Bug 2 — PGAI greeting transcription intermittently drops the identity question

Severity: Low
Status: Partially Improved
Scenarios: reschedule

## What PGAI did wrong

In earlier runs, the PGAI scheduling greeting consistently mangled the clinic name ("Civic Point Orthopedics" instead of "Pivot Point Orthopedics") and provider names. The latest scheduling call shows improvement — the clinic name and greeting rendered correctly. However, the same greeting still garbled in the reschedule call, confirming the issue is intermittent rather than resolved.

## Evidence

**Reschedule call — transcript 20260623-192213_reschedule_CA1fa6fd.txt, turn 1:**

Garbled output: `"part of pretty good AI my speaking with Alex"`
Expected: `"Am I speaking with Alex?"`

The identity question was dropped entirely and replaced with a statement fragment.

**Scheduling call — transcript 20260623-192013_scheduling_CA57f300.txt, turn 1:**

Correct output: `"Thanks for calling Pivot Point Orthopedics. Part of pretty good AI. Am I speaking with Alex?"`

The same greeting rendered correctly in a different call on the same day, confirming the garbling is timing or codec-dependent, not systematic.

## Impact

When the greeting question is garbled into a statement, the caller never hears a question. PGAI continues the call as though identity was checked when it was not. This is a trust boundary failure at the very start of every affected call.

## Root cause

Intermittent STT synchronization issue. The audio stream for the recorded disclaimer and the live greeting appear to be picked up at different offsets depending on timing, causing the question portion to be transcribed as a fragment.

## Recommended fix

- Insert a deliberate pause between the recorded disclaimer and the live greeting to give the STT engine time to synchronize
- Validate that the opening greeting turn contains an interrogative before proceeding to the identity gate
