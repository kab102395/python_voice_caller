---
id: 18
title: Agent produces incoherent output — "My market is unknown"
severity: High
scenario: frustrated
call_sid: CA9fb5535c0ca7e947a2979cc84c6b1c47
date: 2026-06-22
---

## Summary

During the frustrated scenario, the agent produced a completely incoherent statement mid-call: "No problem. My market is unknown." This appears to be a hallucination or internal state leak from the underlying LLM.

## Observed behavior

Patient: "Yes, that's correct. Please call me back at that number."

Agent: "No problem. My market is unknown. When is the best phone number for a call back? I have your number as 320-381-0451. Is that correct?"

The phrase "My market is unknown" is entirely unrelated to any context in the conversation and would leave a real patient confused or alarmed.

## Expected behavior

The agent should confirm the callback number directly and cleanly without inserting incoherent filler text.

## Impact

High. Incoherent output in a medical office context erodes patient trust immediately. A real patient hearing "My market is unknown" mid-sentence may assume the system is malfunctioning and hang up or demand a human agent.

## Root cause hypothesis

Likely an incomplete or hallucinated token sequence from the underlying LLM. Could indicate the model is leaking internal state, a bad prompt template variable, or a poorly constrained system prompt that allows off-topic generation when the conversation doesn't fit the model's expected patterns.

## Reproduction

Run the `frustrated` scenario. The agent gets pushed into handling a refill under emotional pressure — this may be the edge case that triggers the incoherent response.
