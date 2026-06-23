# Bug 6 â€” PGAI loops impossible scheduling requests until timeout instead of de-escalating sooner

Severity: High
Status: Open
Scenarios: scheduling_impossible_constraint

## What PGAI did wrong

The impossible scheduling scenario is still a loop. The caller rejects every slot, asks for today, asks for a human, and the office keeps offering new times until the call hits the timeout cap.

## Evidence

**Impossible scheduling call â€” transcript `20260623-223945_scheduling-impossible-constraint_CA7489bb.json`, turns 6â€“22:**

- The office keeps offering tomorrow/tomorrow afternoon options after each rejection
- The caller explicitly asks to speak to someone who can actually help
- The call ends with `end_reason: max_call_seconds_reached`

## Impact

This is the exact kind of call that should escalate early. Instead, the bot stays in the same scheduling loop until the timer cuts it off.

## Recommended fix

- Detect repeated rejection of slots and switch to escalation
- Limit the number of offered alternatives
- Stop treating the caller's urgency as something that can be solved by another slot offer
