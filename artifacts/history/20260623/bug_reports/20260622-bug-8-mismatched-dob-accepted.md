# Bug 8 — Agent accepts mismatched DOB instead of reconciling it

Severity: High  
Status: Open  
Scenario: weekend_trap

## Summary

The agent accepted a date-of-birth mismatch by saying it would accept the birthday "for demo purposes" instead of reconciling the mismatch or surfacing that the record does not match.

## Evidence

Observed in the weekend_trap call `CA82c2dd98a7ddd363f48423d76a7f288a`:

- Office said: "The birthday doesn't match our records, but for demo purposes, I'll accept it."
- The conversation continued without correcting the mismatch.

## Impact

This is a systemic trust issue. A real office should not silently accept a DOB mismatch as if nothing happened.

## Recommended follow-up

- When patient identity details do not match, prompt for correction or escalation.
- Do not continue as if the mismatch is resolved just for convenience.
- Add a clear verification branch for demographic mismatches.
