# Bug 16 — Refill-style dead end appears again under stress

Severity: Medium  
Status: Open  
Scenario: frustrated

## Summary

The frustrated scenario ran into the same refill-style dead end pattern: medication details were not resolved cleanly, and the call stalled until the hard stop logic ended it.

## Evidence

Observed in the frustrated call `CA9fb5535c0ca7e947a2979cc84c6b1c47`:

- The agent asked about medication details.
- The caller could not provide a clear answer.
- The conversation then drifted into fallback-style responses before ending.

## Impact

This shows the refill dead-end pattern is not isolated to the refill scenario. Under stress, the call still lacks a clean recovery path.

## Recommended follow-up

- Add a clearer fallback branch for ambiguous refill details.
- If the caller is frustrated, route to a concise human-help path sooner.
