# Bug 6 — Agent gets stuck demanding pharmacy location details

Severity: High  
Status: Open  
Scenario: controlled_refill

## Summary

The agent repeatedly demanded pharmacy address, city, cross streets, nearby landmarks, zip code, and fax number instead of accepting the patient’s preferred pharmacy as enough information.

## Evidence

Observed in the controlled refill call `CA63386126eca163ac0be4482248ebe40b`:

- The patient said their preferred pharmacy was Walgreens.
- The agent continued asking for increasingly detailed location information.
- This continued across two consecutive turns and was the main reason the call ran until the hard stop.

## Impact

This is a major UX failure. In a real call, the office should be able to look up a known pharmacy from a simple name or use the one on file, rather than forcing the caller to provide a full address breakdown.

## Recommended follow-up

- Accept the pharmacy name as sufficient when possible.
- Use the pharmacy already on file when available.
- Only ask for additional location detail if there are multiple ambiguous matches.
