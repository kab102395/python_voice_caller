---
name: reschedule-hangs-up-on-confirmation-question
description: During reschedule, when PGAI asks "is this the appointment you want to reschedule?", the patient bot treats it as a closing cue and hangs up, ending the call prematurely.
metadata:
  type: project
---

# Bug 6 — Reschedule call ends prematurely when agent asks appointment confirmation question

Severity: Medium
Status: Open
Scenarios: reschedule

## What happened

During the reschedule scenario, PGAI correctly identified the existing appointment and asked:

> "Alex, I see you have a follow-up appointment with Kelly Noble MD on Friday, July 10th at 1pm at Nashville, 220 Athens Way. Is this the appointment you want to reschedule?"

At this point (turn 5), the call should have continued with the patient confirming and then selecting a new time. Instead, the call ended at turn 6 with the patient saying "Thanks, that helps. Bye."

Transcript: 20260623-192213_reschedule_CA1fa6fd.txt, 6 turns, completed prematurely.

## Why it's a problem

The call ended before any actual rescheduling took place. From PGAI's perspective, the caller hung up without completing the request. No new slot was offered or confirmed. The scenario produced a clean-sounding ending that hid a complete failure to achieve the objective.

## How it was found

Reviewing the reschedule transcript after running the full batch. The call only had 6 turns — far fewer than expected for a completed reschedule. Cross-referencing the turn text showed the goodbye fired on a mid-flow confirmation question, not an actual call wrap-up.

## How we maintained flow

We identified that our patient bot's goodbye detection pattern was triggering on phrases like "is this the appointment you want to reschedule?" which superficially resembles a wrap-up question. We added a `CONFIRMATION_RE` pattern to the reply engine that catches these appointment confirmation questions and returns a short affirmative ("Yes, that's correct.") with `should_hangup=False`, keeping the call alive so PGAI can continue to the slot selection step.

## Recommended fix for PGAI

No fix needed on PGAI's side for this specific turn — the question is correct. This was a calibration issue in our patient simulator that has been corrected.
