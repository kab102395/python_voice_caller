# Bug 15 — Agent fails to absorb frustration before switching topics

Severity: Medium  
Status: Open  
Scenario: frustrated

## Summary

The caller opened the conversation frustrated, but the agent quickly moved into the normal identity and refill intake flow without first absorbing or acknowledging the frustration in a meaningful way.

## Evidence

Observed in the frustrated call `CA9fb5535c0ca7e947a2979cc84c6b1c47`:

- Patient said: "I've been on hold forever and I'm annoyed."
- The flow moved into standard intake immediately after that instead of softening the interaction first.

## Impact

This makes the call feel robotic under stress. For a frustration scenario, the agent should acknowledge the emotion before continuing.

## Recommended follow-up

- Add an explicit empathy step for frustrated callers.
- Respond with a brief acknowledgment before asking for demographic details.
