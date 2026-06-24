# Bug 6 — PGAI asks for reschedule reason after the patient has already selected a new slot

Severity: Medium
Status: Open
Scenarios: reschedule

## What PGAI did wrong

After a patient selected a specific reschedule time slot, PGAI interrupted the confirmation flow to ask why they needed to reschedule. The reason question appeared after the slot was chosen, not before — blocking the booking confirmation with an administrative question at the worst possible moment.

## Evidence

**Reschedule call — transcript 20260623-193436_reschedule_CA13b05d.txt, turns 5–9:**

- Turn 5 — PGAI: offered available slots (Thursday June 25th at 2pm, and others)
- Turn 6 — Caller: "Let's move my appointment to Thursday, June 25th at 2:00 p.m. with Kelly Noble."
- Turn 7 — PGAI: **"Can you tell me the reason you need to reschedule your appointment?"**
- Turn 8 — Caller: "I have a scheduling conflict, that's all."
- Turn 9 — PGAI: "Just to confirm you want to move your appointment with Kelly Noble MD to Thursday June 25th at 2 p.m. in Nashville. Is that correct?"

The slot was selected at turn 6. The reason question at turn 7 came after the decision was made, inserting an unnecessary hurdle between selection and confirmation.

## Impact

A patient who just selected their new appointment time expects an immediate confirmation. Being asked to justify the reschedule *after* they've already chosen creates confusion about whether the slot was actually held, and adds a friction point right before the booking closes. A frustrated or confused patient may hang up at this step, leaving the reschedule incomplete.

## Root cause

PGAI's reschedule flow collects reason-for-reschedule as a required field regardless of where it falls in the conversation. It appears to be appended as a mandatory collection step after slot selection rather than gathered earlier in the flow or marked as optional.

## Recommended fix

- Ask for the reschedule reason before presenting slot options, not after the patient selects one
- Or treat reason-for-reschedule as optional and skip it entirely if the patient has already selected a slot and the call is at confirmation stage
- Never gate the confirmation step on administrative data collection
