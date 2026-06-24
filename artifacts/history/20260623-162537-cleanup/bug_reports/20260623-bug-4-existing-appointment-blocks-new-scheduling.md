# Bug 4 — PGAI blocks new appointment scheduling when an existing appointment is on the account

Severity: High
Status: Open
Scenarios: scheduling

## What PGAI did wrong

When a caller requests a new appointment and PGAI detects an existing appointment on the account, it immediately refuses to schedule anything new. It offers only to reschedule or cancel the existing appointment, or transfer to a team member. No clarifying question is asked. The caller's request is denied outright.

## Evidence

**Scheduling call — transcript 20260623-192013_scheduling_CA57f300.txt, turn 5:**

- Caller (turn 4): "I need to schedule a routine follow-up appointment for next week. Do you have anything available Friday afternoon?"
- PGAI (turn 5): "It looks like you already have a follow-up appointment booked. I can help you reschedule or cancel it if you'd like, or I can connect you to a team member for more help. What would you like to do?"

The caller never asked to reschedule. They asked to book a new appointment. PGAI blocked the request without asking a single clarifying question.

## Impact

A patient may legitimately need a second appointment — a different provider, a different issue, or a different date. Blocking that without any clarification is a hard failure. The call ends with the patient transferred rather than scheduled, and PGAI never attempted to fulfill the original request.

## Root cause

PGAI's scheduling logic appears to use an exclusive gate: if an appointment exists for the appointment type requested, no new booking is allowed. There is no branch that asks whether the patient wants to book in addition to or instead of the existing one.

## Recommended fix

When an existing appointment is detected, ask a clarifying question before blocking:
> "I see you already have a follow-up appointment on [date]. Are you looking to add a new appointment, or would you like to reschedule that one?"

Do not deflect to a transfer without first giving the caller a path to accomplish their stated goal.
