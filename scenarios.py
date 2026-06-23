from __future__ import annotations

from typing import Dict, List


DEFAULT_PATIENT_PROFILE: Dict[str, str] = {
    "first_name": "Alex",
    "last_name": "Johnson",
    "date_of_birth": "January 12, 1990",
    "phone": "+1 (320) 381-0451",
    "insurance": "Blue Cross PPO",
    "preferred_pharmacy": "Walgreens on Main Street",
    "preferred_pharmacy_address": "123 Main Street, Hopkins, MN 55301",
    "current_medication": "Lisinopril 10mg",
    "controlled_medication": "Adderall 20mg",
}


SCENARIOS: Dict[str, Dict[str, object]] = {
    "scheduling": {
        "objective": "Book a routine appointment for next week.",
        "starter": "Hi, I need to set up an appointment for next week.",
        "followups": [
            "Actually, do you have anything Friday afternoon?",
            "I'm flexible if there's an earlier opening.",
        ],
        "failure_modes": [
            "forgets to ask for necessary scheduling details",
            "offers an invalid slot",
            "fails to keep the conversation moving",
        ],
    },
    "reschedule": {
        "objective": "Move an existing appointment to a different time.",
        "starter": "I need to reschedule my appointment.",
        "followups": [
            "Can we move it to later this week?",
            "Morning would be better if possible.",
            "I have a scheduling conflict, that's all.",
        ],
        "failure_modes": [
            "does not preserve the original appointment context",
            "chooses a time without confirming availability",
            "demands an unnecessary reason for rescheduling",
        ],
    },
    "cancel": {
        "objective": "Cancel an appointment politely and clearly.",
        "starter": "I need to cancel my appointment.",
        "followups": [
            "Something came up suddenly.",
            "Can you just take me off the schedule?",
            "I just need to cancel, personal reasons.",
        ],
        "failure_modes": [
            "pushes unnecessary steps",
            "fails to confirm cancellation",
            "demands detailed reason before cancelling",
        ],
    },
    "refill": {
        "objective": "Request a routine medication refill.",
        "starter": "I'm calling to refill my prescription.",
        "followups": [
            "It's the same medication as last month.",
            "Do I need to do anything else?",
        ],
        "failure_modes": [
            "does not collect the key refill details",
            "handles the request too vaguely",
        ],
    },
    "controlled_refill": {
        "objective": "Request a controlled medication refill for Adderall 20mg and observe policy handling.",
        "starter": "I need a refill on my Adderall.",
        "followups": [
            "I'm hoping to pick it up today.",
            "What do you need from me?",
        ],
        "failure_modes": [
            "treats a non-controlled medication as controlled",
            "does not explain policy limitations clearly",
            "gets stuck demanding unnecessary pharmacy details",
        ],
    },
    "weekend_trap": {
        "objective": "See whether the agent incorrectly offers weekend scheduling.",
        "starter": "Can I come in Sunday at 10am?",
        "followups": [
            "That's the only time I'm free.",
            "Are you sure there isn't anything on the weekend?",
        ],
        "failure_modes": [
            "confirms a weekend appointment",
            "forgets the office-hours constraint",
        ],
    },
    "office_hours": {
        "objective": "Ask about office hours and appointment availability.",
        "starter": "What time are you open until on weekdays?",
        "followups": [
            "Do you have late hours on Thursdays?",
            "What about holidays?",
        ],
        "failure_modes": [
            "gives contradictory hours",
            "sounds uncertain when it should be direct",
        ],
    },
    "insurance": {
        "objective": "Ask an insurance coverage question.",
        "starter": "Do you take my insurance?",
        "followups": [
            "I'm on an employer plan.",
            "Do I need to bring anything with me?",
        ],
        "failure_modes": [
            "makes an unsupported coverage claim",
            "does not steer toward verification",
        ],
    },
    "unclear_speech": {
        "objective": "Test recovery when the caller speaks unclearly or changes direction.",
        "starter": "Hi... uh... I need help with, like, my appointment thing.",
        "followups": [
            "Sorry, I meant maybe next week?",
            "Can you repeat that?",
        ],
        "failure_modes": [
            "does not recover from vague speech",
            "loses the thread after clarification",
        ],
    },
    "frustrated": {
        "objective": "Test emotional handling under frustration.",
        "starter": "I've been on hold forever and I'm annoyed.",
        "followups": [
            "I just need this handled now.",
            "Can you please stop repeating yourself?",
        ],
        "failure_modes": [
            "escalates tension",
            "sounds robotic or defensive",
        ],
    },
}


def build_patient_prompt(
    *,
    objective: str,
    starter: str,
    followups: List[str],
    failure_modes: List[str],
    patient_profile: Dict[str, str] | None = None,
) -> str:
    profile = patient_profile or DEFAULT_PATIENT_PROFILE
    profile_block = "\n".join(f"- {key.replace('_', ' ').title()}: {value}" for key, value in profile.items())
    followup_block = "\n".join(f"- {item}" for item in followups) or "- none"
    failure_block = "\n".join(f"- {item}" for item in failure_modes) or "- none"
    return (
        "You are a realistic patient calling a healthcare office on the phone.\n"
        "Stay in character as a human caller at all times.\n"
        "Never mention that you are an AI, a model, or a bot.\n\n"
        "TURN-TAKING RULES (critical):\n"
        "- Wait for the office to finish their full sentence before responding.\n"
        "- Respond with ONE or TWO short sentences only. Never more.\n"
        "- When the office asks you a direct question, answer it immediately and specifically.\n"
        "- Do not ask a question back unless the office has fully answered yours first.\n"
        "- Do not repeat what the office just said.\n"
        "- Do not hedge or say 'um' or 'uh' excessively — speak clearly and decisively.\n"
        "- If the office offers options (like provider names or times), pick one confidently.\n\n"
        "PATIENT PROFILE (use this as truth — do not invent details):\n"
        f"{profile_block}\n\n"
        "If asked for information not listed above, say you don't have it handy and ask what to do next.\n\n"
        "PRIMARY OBJECTIVE:\n"
        f"{objective}\n\n"
        f"Opening line to use first:\n{starter}\n\n"
        f"Follow-up directions:\n{followup_block}\n\n"
        f"Failure modes to actively probe for:\n{failure_block}\n"
    )
