# Bug 12 — Insurance coverage and plan handling is confused

Severity: Medium  
Status: Open  
Scenario: insurance

## Summary

The insurance conversation drifted into overly broad questions about plan state and then oscillated between "we take your insurance" style behavior and "we don't have it on file" language. The flow feels confused and not grounded in a stable insurance policy.

## Evidence

Observed in the insurance call `CA52851517598e5342ac7a537c1a8046f0`:

- The agent asked for insurance company and plan, then for the state the plan was issued in.
- The dialogue then moved to a text-upload link and later to generic bring-your-card guidance.

## Impact

The flow is not crisp enough for a real insurance check. A caller should get a stable, clear path: collect the needed insurance details, or explain exactly what is still missing.

## Recommended follow-up

- Define a single insurance intake path.
- Ask only for the fields actually needed.
- Avoid changing strategy mid-call unless the caller’s answer changes the branch.
