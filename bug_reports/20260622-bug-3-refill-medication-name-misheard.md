# Bug 3 — Medication name is misheard and not corrected

Severity: Medium  
Status: Open  
Scenario: refill

## Summary

In the refill flow, the office-side speech recognition misheard the medication name as "LIC Pro" instead of "Lisinopril". The agent then continued the conversation without correcting or reconfirming the medication name.

## Evidence

Observed in the refill call `CAdcd451b596109a9618c97ec22e66e118`:

- Patient intended: "Lisinopril 10mg"
- Office transcript included: "How many days of LIC Pro do you have left"

## Impact

If this were a real refill, the wrong medication could be processed or the agent could proceed on a misheard medication name.

## Recommended follow-up

- Confirm medication names before proceeding when the transcript is uncertain.
- Add a clarification step when the medication string is low-confidence or obviously garbled.
- Consider prompting the patient to spell the medication name or read it from the bottle when needed.
