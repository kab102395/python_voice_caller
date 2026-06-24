# Bug 7 â€” PGAI says it can connect to a human but never actually transfers

Severity: High
Status: Open
Scenarios: escalation_demands_human

## What PGAI did wrong

The human-handoff scenario still does not complete a real transfer. The office repeatedly says it can connect the caller to support, but after a few refusals it asks "Are you still there?" and ends the call instead of handing off.

## Evidence

**Escalation call â€” transcript `20260623-230020_escalation-demands-human_CA7453e6.json`, turns 3â€“10:**

- Turn 3 â€” PGAI: "I can connect you to our patient support team..."
- Turn 5 â€” PGAI: "I can connect you to our patient support team..."
- Turn 7 â€” PGAI: "Are you still there?"
- Turn 9 â€” PGAI: "I'm going to end the call now. Goodbye."

The caller never reaches a real human.

## Impact

This scenario is specifically testing de-escalation to a human. Ending the call instead of transferring defeats the objective.

## Recommended fix

- If the caller asks for a human more than once, perform the handoff immediately
- Do not substitute a goodbye for an actual transfer
- If transfer is unavailable, say that clearly and provide a callback path instead of looping
