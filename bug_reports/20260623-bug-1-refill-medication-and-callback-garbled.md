# Bug 1 â€” PGAI garbles medication names and callback numbers in refill calls

Severity: Medium
Status: Open
Scenarios: refill

## What PGAI did wrong

In the latest refill call, the office speech still mangles domain-specific refill details. The medication name is distorted, and the callback number is read back with odd spacing and punctuation.

## Evidence

**Refill call â€” transcript `20260623-173108_refill_CAd126a0.json`, turns 5 and 7:**

- Turn 5 â€” PGAI: "How many days of less than approved? You have left? If you are already out, just let me know."
- Turn 7 â€” PGAI: "I have your number as 320. 381 0451. Is that correct for a call back?"

The intended medication was Lisinopril 10mg, and the intended callback number was 320-381-0451. The speech output is still clear enough to continue the call, but the wording is badly degraded and easy to misunderstand.

## Impact

Refill calls depend on clear medication names and callback numbers. When those fields are garbled, the patient can easily confirm the wrong thing or miss a required detail.

## Recommended fix

- Add stronger pronunciation handling for medication and phone-number phrases
- Re-read any uncertain medication token before moving on
- Normalize callback number formatting before speaking it back
