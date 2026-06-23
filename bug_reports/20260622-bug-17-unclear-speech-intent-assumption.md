---
id: 17
title: Agent assumes reschedule intent from vague "appointment thing"
severity: Medium
scenario: unclear_speech
call_sid: CA854f38a1dd5d7229464f5a68838c642c
date: 2026-06-22
---

## Summary

When a patient opened with intentionally vague language ("I need help with, like, my appointment thing"), the agent immediately pulled up the patient's existing appointment and offered confirm/reschedule/cancel options — without first asking what kind of help was needed.

## Observed behavior

Patient: "Hi, yes, this is Alex. I need help with, like, my appointment thing."

Agent (next turn): "You have a follow-up appointment, scheduled for tomorrow, Tuesday June 23rd at 10:00 a.m. with Dr. Doozy Howser. Would you like to confirm, reschedule, or cancel this appointment?"

## Expected behavior

The agent should ask a clarifying question before assuming intent. "Help with my appointment thing" could mean billing, directions, what to bring, insurance questions, or many other things.

## Impact

Low friction in this call because the patient happened to want a reschedule. But a patient calling about a billing dispute or travel directions would be sent down the wrong path entirely, requiring a re-prompt and extra call time.

## Notes

The agent got lucky here. This is a dangerous pattern at scale.
