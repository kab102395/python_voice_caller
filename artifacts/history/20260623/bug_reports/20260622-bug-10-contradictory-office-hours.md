# Bug 10 — Office-hours answers are contradictory

Severity: Medium  
Status: Open  
Scenario: office_hours

## Summary

The office-hours responses were internally inconsistent across turns. The call gave one set of weekday hours, then corrected or contradicted them later, which makes the flow hard to trust.

## Evidence

Observed in the office_hours call `CA5096bcdc278ed9606f85d036309eb6c3`:

- One response said the office was open until 4 p.m. on Monday, Tuesday, and Thursday, 7 p.m. on Wednesday, and noon on Friday.
- A later response said they close at 4 p.m. on Thursdays and that Wednesday is the latest hour.

## Impact

Conflicting hours are a trust failure. A caller could leave with the wrong schedule information and make a bad decision based on it.

## Recommended follow-up

- Keep office-hours responses consistent across the call.
- Use one canonical hours table for the scenario.
- If the caller asks a follow-up, answer with a stable repetition of the same schedule rather than generating a new variant.
