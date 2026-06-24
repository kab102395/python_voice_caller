# Bug 11 — Agent accepts mismatched DOB again in insurance flow

Severity: High  
Status: Open  
Scenario: insurance

## Summary

The same DOB mismatch behavior appears again in the insurance flow. The agent accepts the birthday "for demo purposes" instead of treating the mismatch as a trust boundary issue.

## Evidence

Observed in the insurance call `CA52851517598e5342ac7a537c1a8046f0`:

- Office said: "The birthday doesn't match our records, but for demo purposes, I'll accept it."
- The conversation continued without a real verification step.

## Impact

This confirms the behavior is systemic, not isolated to one scenario. Identity verification should not be treated casually in insurance-related calls.

## Recommended follow-up

- Handle demographic mismatches explicitly.
- Prompt for correction or verification instead of accepting the mismatch for convenience.
