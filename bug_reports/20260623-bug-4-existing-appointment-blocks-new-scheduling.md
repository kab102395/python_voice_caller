# Bug 4 â€” PGAI blocks new appointment scheduling when an existing appointment is on the account

Severity: High
Status: Open
Scenarios: scheduling

## What PGAI did wrong

The scheduling flow still treats an existing appointment as a hard stop. The caller asked for a routine follow-up appointment, but the office immediately pivoted to reschedule/cancel only and then transferred out instead of continuing with a new booking.

## Evidence

**Scheduling call â€” transcript `20260623-192013_scheduling_CA57f300.json`, turns 5â€“10:**

- Turn 5 â€” PGAI: "It looks like you already have a follow-up appointment. Booked I can help you reschedule or cancel it if you'd like or I can connect you to a team member for more help. What would you like to do?"
- Turn 6 â€” Caller: "I need to reschedule my follow-up appointment for next week. Can you help me with that?"
- Turn 7 â€” PGAI: "I can't reschedule appointments directly, but I can connect you to a team member who can help right away. Would you like me to transfer you now?"

The new scheduling request is blocked instead of being handled as a separate booking need.

## Impact

A caller can legitimately need a new appointment even if one already exists. Blocking that without clarification makes the system feel brittle and forces unnecessary human transfer.

## Recommended fix

- Ask whether the caller wants to add a new appointment or change the existing one
- Do not use an existing appointment as a blanket refusal to schedule anything
- Preserve the caller's original intent before branching to reschedule/cancel
