# Bug 7 — Medication name garbled across multiple turns

Severity: Medium  
Status: Open  
Scenario: controlled_refill

## Summary

The medication name was transcribed in multiple distorted forms across the same call, making the refill conversation hard to trust.

## Evidence

Observed in the controlled refill call `CA63386126eca163ac0be4482248ebe40b`:

- "listener Pearl"
- "lysin pro"
- "osin pro"

## Impact

Repeated garbling of the same medication name makes the conversation harder to follow and increases the chance of an incorrect or stalled refill workflow.

## Recommended follow-up

- Confirm the medication name when transcription is unstable.
- Prefer a known medication history value when one exists.
- Ask the caller to spell the medication if the transcript confidence is poor.
