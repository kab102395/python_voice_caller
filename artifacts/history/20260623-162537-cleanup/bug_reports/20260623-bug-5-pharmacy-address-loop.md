# Bug 5 — PGAI loops demanding full pharmacy address and will not accept a pharmacy name alone

Severity: High
Status: Open
Scenarios: refill

## What PGAI did wrong

When a caller provides a pharmacy name during a refill request, PGAI refuses to accept it and begins demanding increasingly granular address information in a loop — city, state, zip code, cross streets, nearby landmarks, phone number, and fax number. The refill cannot proceed until all of this is provided, and the agent never offers to use the pharmacy already on file.

## Evidence

**Refill call — transcript 20260623-192346_refill_CAb84a28.txt, turns 9–14:**

- Turn 9 — PGAI: "Could you please provide the name of the pharmacy you want to use... address, city, cross streets, phone or fax number, please share that as well."
- Turn 10 — Caller: "Walgreens on Main Street."
- Turn 11 — PGAI: "Could you tell me the city and state where this Walgreens is located?"
- Turn 12 — Caller: gave city/state
- Turn 13 — PGAI: "If you are able to remember any nearby landmarks, cross streets, or the zip code... would you like to try that or use a different pharmacy?"
- Turn 14 — Caller: provided full address
- Call ended without the refill being confirmed

PGAI escalated its address demands across three consecutive turns and still did not confirm the refill. The call ended in an unresolved state after 14 turns.

## Impact

A real patient calling in for a medication refill should never need to provide a full postal address, fax number, and cross streets during a voice call. This is an unreasonable data requirement for the phone channel. It causes call failure for any patient who does not have their pharmacy's full address memorized.

## Root cause

PGAI's pharmacy data collection step appears to require a fully structured address record before it can proceed. It has no fallback to accept a well-known chain pharmacy name ("Walgreens"), no option to use the pharmacy on file, and no escalation path that bypasses the address requirement.

## Recommended fix

- Accept a nationally recognized pharmacy chain name and location ("Walgreens on Main Street") without requiring a full postal address
- Before asking for pharmacy details, check whether the patient's account already has a pharmacy on file and offer to use it
- Cap pharmacy address prompts at one follow-up — if the caller cannot provide the address, escalate to a staff callback rather than looping indefinitely
