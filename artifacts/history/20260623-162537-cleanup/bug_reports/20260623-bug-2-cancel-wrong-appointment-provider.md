# Bug 2 â€” PGAI pulls the wrong appointment into cancel calls

Severity: High
Status: Open
Scenarios: cancel

## What PGAI did wrong

In the current cancel call, PGAI identifies the wrong appointment and the wrong provider before asking for cancellation confirmation. The caller asked to cancel Dr. Zbigniew Lukoski on Thursday, June 26, but the office kept referring to a different appointment with Kelly Noble on Friday, July 10.

## Evidence

**Cancel call â€” transcript `20260623-192658_cancel_CAd8f7a4.json`, turns 5â€“9:**

- Turn 5 â€” PGAI: "You have an appointment with Kelly Noble on Friday July 10th. Is this the appointment you want to cancel?"
- Turn 6 â€” Caller: "I need to cancel my appointment with Dr. Zbigniew Lukoski on Thursday, June 26 at 2:00 p.m."
- Turn 7 â€” PGAI: "I do not see an upcoming appointment with Dr. Big moo Lukowski on Thursday June 26th. The only appointment I see is with Kelly Noble on Friday July 10th..."

The call only resolves by transferring the caller to a representative.

## Impact

A cancel call should identify the appointment the caller actually means. Pulling the wrong appointment creates immediate trust loss and can lead to canceling the wrong visit.

## Recommended fix

- Confirm the provider/date that the caller gave before looking at alternate appointments
- Do not overwrite a specific appointment request with a different appointment from the account
- If the requested appointment cannot be found, explain that directly instead of substituting another one
