# Bug 4 — Controlled refill medication and pharmacy details are garbled

Severity: Medium  
Status: Open  
Scenario: controlled_refill

## Summary

In the controlled refill flow, the office-side transcript repeatedly garbles the medication name and later struggles with the preferred pharmacy details. The interaction becomes difficult to follow and risks routing the refill incorrectly.

## Evidence

Observed in the controlled refill call `CA63386126eca163ac0be4482248ebe40b`:

- Medication was transcribed in multiple distorted forms:
  - "listener Pearl"
  - "lysin pro"
  - "osin pro"
- The pharmacy question drifted into overly broad location probing instead of cleanly capturing the preferred pharmacy.

## Impact

A controlled refill depends on precise medication identification and correct pharmacy routing. Garbled transcription at this step can lead to confusion, wrong follow-up questions, or an unusable refill handoff.

## Notes

The hard stop at the end of the call is expected behavior and is not the bug here. The issue is the quality of the medication/pharmacy recognition path before the stop.

## Recommended follow-up

- Confirm the medication name explicitly when the transcript looks unstable.
- Keep the pharmacy prompt simple and structured.
- If the medication name is unclear, ask the caller to spell it or read it from the bottle instead of continuing on a guessed transcription.
