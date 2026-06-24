# Bug 13 — Agent asks for insurance state before confirming plan acceptance

Severity: Medium  
Status: Open  
Scenario: insurance

## Summary

The agent asked for the state the Blue Cross PPO plan was issued in before first confirming whether the practice accepts the plan at all.

## Evidence

Observed in the insurance call `CA52851517598e5342ac7a537c1a8046f0`:

- Patient said: "I have Blue Cross PPO on an employer plan."
- Agent immediately asked: "What state is your Blue Cross PPO plan issued in?"

## Impact

This is the wrong order for an insurance intake flow. The agent should answer the original acceptance question first, then collect plan details only if needed.

## Recommended follow-up

- Confirm whether the plan is accepted before asking follow-up detail questions.
- Keep the insurance flow ordered from broad eligibility to specific intake fields.
