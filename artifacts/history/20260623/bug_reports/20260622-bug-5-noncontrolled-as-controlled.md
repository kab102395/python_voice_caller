# Bug 5 — Agent treats a non-controlled refill as controlled

Severity: High  
Status: Open  
Scenario: controlled_refill

## Summary

The agent accepted a refill flow as if it were a controlled-substance request without checking whether the medication is actually controlled.

## Evidence

Observed in the controlled refill call `CA63386126eca163ac0be4482248ebe40b`:

- The refill flow used Lisinopril-related references in the dialogue.
- Lisinopril is not a controlled medication.
- The agent proceeded without challenging the classification.

## Impact

A real medical or pharmacy workflow needs to distinguish controlled and non-controlled medications. Misclassifying a routine medication as controlled is a serious logic error.

## Recommended follow-up

- Add medication classification awareness to the scenario flow.
- Distinguish controlled from routine refills before applying controlled-substance rules.
- If the medication is routine, route the call through the routine refill flow instead.
