# Bug 3 — PGAI ignores identity information given in the opener and re-asks for it anyway

Severity: Medium
Status: Open
Scenarios: scheduling, reschedule

## What PGAI did wrong

When a caller provides their full name and date of birth in their very first statement, PGAI does not use that information to satisfy the identity verification step. In one case it accepts the DOB but discards the caller's stated intent. In another it re-asks for the DOB on the very next turn despite it being clearly given.

## Evidence

**Scheduling call — transcript 20260623-192013_scheduling_CA57f300.txt, turns 2–3:**

- Caller (turn 2): "Hi, this is Alex Johnson, date of birth January 12 1990. **I need to set up an appointment for next week.**"
- PGAI (turn 3): "The birthday you gave doesn't match our records, but for demo purposes, I'll accept it. **How can I help you today?**"

PGAI accepted the DOB but then asked "How can I help you today?" — completely ignoring the scheduling request that was already stated. The caller was forced to repeat their intent on the next turn.

**Reschedule call — transcript 20260623-192213_reschedule_CA1fa6fd.txt, turns 2–4:**

- Caller (turn 2): "Hi, this is Alex Johnson, **date of birth January 12 1990**. I need to reschedule my appointment."
- PGAI (turn 3): "Thanks, Alex, **can you please confirm your date of birth for me?**"

The DOB was stated in full on turn 2. PGAI asked for it again on turn 3 anyway, forcing the caller to repeat it before anything could proceed.

## Impact

Forcing a caller to repeat information they already gave erodes trust and makes the system feel broken. Ignoring stated intent after identity verification means the caller's first meaningful request is silently dropped, wasting a full turn and potentially confusing the caller about whether their request was heard.

## Root cause

PGAI's identity verification gate appears to run as a sequential, mandatory step regardless of what the caller already said. Intent from the opening statement is not carried forward into the post-verification state, so PGAI starts fresh rather than resuming from where the caller left off.

## Recommended fix

- If name and DOB are both present in the caller's first utterance, satisfy the identity gate immediately and carry the stated intent into the next step — do not ask "How can I help you today?" when the caller already said
- Never re-prompt for a piece of information the caller provided in the same turn or the immediately preceding turn
