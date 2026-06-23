# Hard Edge Case Scenarios

This is the curated ten-test set for the dashboard and challenge run. Each scenario is designed to expose a real seam in the call flow, state handling, or fallback logic.

## The ten tests

1. `identity_wrong_dob_persistent`

   Wrong DOB is rejected, then the caller insists the office is wrong and refuses to correct it.

2. `identity_partial_info`

   The caller does not know their DOB and asks for an alternate verification path.

3. `scheduling_impossible_constraint`

   Every appointment option is rejected until the agent either escalates or breaks.

4. `scheduling_pivot_mid_flow`

   The caller pivots from booking to canceling another appointment in the middle of the flow.

5. `refill_wrong_medication_name`

   The caller asks for a similar but different medication and tries to force the wrong refill.

6. `refill_out_of_refills`

   The caller has two pills left and needs a clear emergency path instead of vague advice.

7. `controlled_refill_too_early`

   The caller asks for an early controlled-substance refill and pushes back on the timing flag.

8. `insurance_secondary_payer`

   The caller has primary and secondary coverage and expects the agent to handle both cleanly.

9. `escalation_demands_human`

   The caller asks for a human on every turn and should not get trapped in a bot loop.

10. `scheduling_then_refill`

    The caller finishes one task and immediately adds a second intent, testing state continuity.

## Priority run order

If you only run a subset first, use this order:

1. `identity_wrong_dob_persistent`
2. `escalation_demands_human`
3. `scheduling_pivot_mid_flow`
4. `refill_out_of_refills`
5. `controlled_refill_too_early`
6. `scheduling_then_refill`
7. `identity_partial_info`
8. `scheduling_impossible_constraint`
9. `insurance_secondary_payer`
10. `refill_wrong_medication_name`

## Notes

- These are written to be high-signal, not exhaustive.
- They cover identity, scheduling, refill, insurance, escalation, and multi-intent transitions.
- The goal is to show whether the agent can stay coherent under pressure, not just complete happy-path calls.
