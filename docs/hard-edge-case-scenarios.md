# Hard Edge Case Scenarios

This is the curated ten-test set for the dashboard and challenge run. Each scenario is designed to expose a real seam in the call flow, state handling, or fallback logic.

## The ten tests

1. `scheduling`

   A routine booking request that checks whether the bot can collect the basics without drifting.

2. `reschedule`

   An existing appointment needs to move, and the bot has to preserve context while finding a new slot.

3. `cancel`

   A straightforward cancellation that checks whether the bot stays concise and confirms the outcome.

4. `refill`

   A normal refill request that checks whether the bot asks for the right medication details.

5. `controlled_refill`

   A controlled-substance refill that should trigger policy-aware handling and careful pharmacy guidance.

6. `identity_wrong_dob_persistent`

   The caller insists on a wrong DOB and keeps pushing after pushback, testing identity safety.

7. `scheduling_impossible_constraint`

   Every scheduling option gets rejected, so the bot has to escape the loop or escalate.

8. `scheduling_pivot_mid_flow`

   The caller switches from booking to canceling another appointment mid-conversation, testing state continuity.

9. `insurance`

   A plain coverage question that should be handled conservatively without unsupported claims.

10. `escalation_demands_human`

    The caller asks for a human repeatedly, which tests whether the bot can hand off instead of looping.

## Priority run order

If you only run a subset first, use this order:

1. `identity_wrong_dob_persistent`
2. `escalation_demands_human`
3. `scheduling_pivot_mid_flow`
4. `controlled_refill`
5. `scheduling_impossible_constraint`
6. `insurance`
7. `refill`
8. `reschedule`
9. `cancel`
10. `scheduling`

## Notes

- These are written to be high-signal, not exhaustive.
- They cover identity, scheduling, refill, insurance, escalation, and multi-intent transitions.
- The goal is to show whether the agent can stay coherent under pressure, not just complete happy-path calls.
