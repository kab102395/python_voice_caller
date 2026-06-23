# Bug 2 — Refill flow has no medication history context

Severity: Medium  
Status: Open  
Scenario: refill

## Summary

When the patient says the medication is "the same as last month," the agent responds that it does not have the medication name on file instead of surfacing prior prescription context or offering a better alternative path.

## Evidence

Observed in the refill call `CA82c99f40c5dec56c451e7a8d585996b0`:

- Patient said: "It's the same medication as last month."
- Agent replied: "I do not have the name of your medication on file"

## Impact

A real patient calling for a routine refill would expect the office to have medication history available. Without that context, the flow feels incomplete and less realistic.

## Recommended follow-up

- Surface medication history in the refill scenario when available.
- If no history exists, explicitly tell the patient that and offer a clear alternative.
- Add a prompt like: "I can see you were last prescribed X, is that the one you need?"
