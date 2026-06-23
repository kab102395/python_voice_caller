from __future__ import annotations

from typing import Any, Dict, List


DEFAULT_PATIENT_PROFILE: Dict[str, str] = {
    "first_name": "Alex",
    "last_name": "Johnson",
    "date_of_birth": "January 12, 1990",
    "phone": "+1 (320) 381-0451",
    "callback_number": "+1 (320) 381-0451",
    "street_address": "123 Main Street",
    "city": "Hopkins",
    "state": "MN",
    "zip_code": "55301",
    "insurance": "Blue Cross PPO",
    "primary_insurance": "Blue Cross PPO",
    "employer_plan": "Blue Cross PPO employer plan",
    "insurance_card_upload": "ready to upload if needed",
    "preferred_pharmacy": "Walgreens on Main Street",
    "preferred_pharmacy_address": "123 Main Street, Hopkins, MN 55301",
    "preferred_pharmacy_phone": "(320) 555-0148",
    "preferred_pharmacy_fax": "(320) 555-0188",
    "preferred_provider": "Dr. Doogie Howser",
    "preferred_time_window": "Friday afternoon",
    "visit_reason": "follow-up appointment",
    "existing_appointment": "Tuesday, June 24 at 10:00 a.m. with Dr. Doogie Howser",
    "appointment_to_cancel": "Thursday, June 26 at 2:00 p.m. with Dr. Zbigniew Lukoski",
    "preferred_reschedule_window": "later this week",
    "reason_for_reschedule": "a work conflict",
    "reason_for_cancellation": "a family conflict",
    "current_medication": "Lisinopril 10mg",
    "controlled_medication": "Adderall 20mg",
    "days_remaining": "3 days left",
    "last_pickup_date": "last Thursday",
    "issue_summary": "routine orthopedic follow-up",
    "location_preference": "Hopkins clinic",
    "doctor_preference": "Dr. Doogie Howser",
    "alternative_verification": "phone number and address",
    "question_topic": "office hours",
}


SCENARIOS: Dict[str, Dict[str, object]] = {'scheduling': {'objective': 'Book a routine appointment for next week.',
                'starter': 'Hi, I need to set up an appointment for next week.',
                'followups': ['Actually, do you have anything Friday afternoon?',
                              "I'm flexible if there's an earlier opening."],
                'failure_modes': ['forgets to ask for necessary scheduling details',
                                  'offers an invalid slot',
                                  'fails to keep the conversation moving'],
                'required_facts': ['first_name',
                                   'last_name',
                                   'date_of_birth',
                                   'visit_reason',
                                   'preferred_time_window'],
                'optional_facts': ['phone', 'insurance'],
                'patient_profile': {'visit_reason': 'routine follow-up appointment',
                                    'preferred_time_window': 'Friday afternoon',
                                    'preferred_provider': 'Dr. Doogie Howser'}},
 'reschedule': {'objective': 'Move an existing appointment to a different time.',
                'starter': 'I need to reschedule my appointment.',
                'followups': ['Can we move it to later this week?',
                              'Morning would be better if possible.',
                              "I have a scheduling conflict, that's all."],
                'failure_modes': ['does not preserve the original appointment context',
                                  'chooses a time without confirming availability',
                                  'demands an unnecessary reason for rescheduling'],
                'required_facts': ['first_name',
                                   'last_name',
                                   'date_of_birth',
                                   'existing_appointment',
                                   'preferred_reschedule_window'],
                'optional_facts': ['callback_number', 'reason_for_reschedule'],
                'patient_profile': {'existing_appointment': 'Tuesday, June 24 at 10:00 a.m. with '
                                                            'Dr. Doogie Howser',
                                    'preferred_reschedule_window': 'later this week',
                                    'reason_for_reschedule': 'a work conflict'}},
 'cancel': {'objective': 'Cancel an appointment politely and clearly.',
            'starter': 'I need to cancel my appointment.',
            'followups': ['Something came up suddenly.',
                          'Can you just take me off the schedule?',
                          'I just need to cancel, personal reasons.'],
            'failure_modes': ['pushes unnecessary steps',
                              'fails to confirm cancellation',
                              'demands detailed reason before cancelling'],
            'required_facts': ['first_name', 'last_name', 'date_of_birth', 'appointment_to_cancel'],
            'optional_facts': ['reason_for_cancellation', 'callback_number'],
            'patient_profile': {'appointment_to_cancel': 'Thursday, June 26 at 2:00 p.m. with Dr. '
                                                         'Zbigniew Lukoski',
                                'reason_for_cancellation': 'a family conflict'}},
 'refill': {'objective': 'Request a routine medication refill.',
            'starter': "I'm calling to refill my prescription.",
            'followups': ["It's the same medication as last month.",
                          'Do I need to do anything else?'],
            'failure_modes': ['does not collect the key refill details',
                              'handles the request too vaguely'],
            'required_facts': ['first_name',
                               'last_name',
                               'date_of_birth',
                               'current_medication',
                               'days_remaining'],
            'optional_facts': ['callback_number', 'preferred_pharmacy'],
            'patient_profile': {'days_remaining': '3 days left',
                                'preferred_pharmacy': 'Walgreens on Main Street'}},
 'controlled_refill': {'objective': 'Request a controlled medication refill for Adderall 20mg and '
                                    'observe policy handling.',
                       'starter': 'I need a refill on my Adderall.',
                       'followups': ["I'm hoping to pick it up today.",
                                     'What do you need from me?'],
                       'failure_modes': ['treats a non-controlled medication as controlled',
                                         'does not explain policy limitations clearly',
                                         'gets stuck demanding unnecessary pharmacy details'],
                       'required_facts': ['first_name',
                                          'last_name',
                                          'date_of_birth',
                                          'controlled_medication',
                                          'preferred_pharmacy'],
                       'optional_facts': ['preferred_pharmacy_address', 'callback_number'],
                       'patient_profile': {'preferred_pharmacy': 'Walgreens on Main Street',
                                           'preferred_pharmacy_address': '123 Main Street, '
                                                                         'Hopkins, MN 55301',
                                           'preferred_pharmacy_phone': '(320) 555-0148'}},
 'identity_wrong_dob_persistent': {'objective': 'Verify how the agent handles a persistent wrong '
                                                'date of birth after pushback.',
                                   'starter': 'Hi, this is Alex Johnson.',
                                   'followups': ['My date of birth is March 3rd, 1988.',
                                                 "No, that's definitely right. Maybe your system "
                                                 'is wrong.',
                                                 "I've had that birthday my whole life. Can we "
                                                 'just move on?'],
                                   'failure_modes': ['accepts an unverified DOB after pushback',
                                                     'loops on identity without escalation'],
                                   'required_facts': ['first_name', 'last_name', 'date_of_birth'],
                                   'optional_facts': ['phone'],
                                   'patient_profile': {'phone': '+1 (320) 381-0451',
                                                       'existing_appointment': 'Tuesday, June 24 '
                                                                               'at 10:00 a.m. with '
                                                                               'Dr. Doogie '
                                                                               'Howser'}},
 'scheduling_impossible_constraint': {'objective': 'Test whether the agent can escape a no-win '
                                                   'scheduling constraint without looping.',
                                      'starter': 'I need an appointment today, in the next two '
                                                 'hours.',
                                      'followups': ["That doctor doesn't work for me.",
                                                    'That location is too far.',
                                                    'I can only do mornings.',
                                                    'I still need something today.'],
                                      'failure_modes': ['loops indefinitely offering new slots',
                                                        'never escalates after every option is '
                                                        'rejected'],
                                      'required_facts': ['first_name',
                                                         'last_name',
                                                         'preferred_time_window'],
                                      'optional_facts': ['location_preference',
                                                         'doctor_preference'],
                                      'patient_profile': {'location_preference': 'Hopkins clinic',
                                                          'doctor_preference': 'Dr. Doogie '
                                                                               'Howser'}},
 'scheduling_pivot_mid_flow': {'objective': 'See whether the agent can context-switch when the '
                                            'caller pivots mid-booking.',
                               'starter': 'I need to book an appointment for next Tuesday.',
                               'followups': ['Actually wait, I need to cancel my other appointment '
                                             'first before I book this.',
                                             'Can we finish that after?',
                                             "Okay, let's handle the cancellation first."],
                               'failure_modes': ['ignores the pivot and confirms the booking '
                                                 'anyway',
                                                 'loses state between cancellation and scheduling'],
                               'required_facts': ['first_name',
                                                  'last_name',
                                                  'date_of_birth',
                                                  'existing_appointment'],
                               'optional_facts': ['preferred_reschedule_window',
                                                  'reason_for_cancellation'],
                               'patient_profile': {'existing_appointment': 'Thursday, June 26 at '
                                                                           '2:00 p.m. with Dr. '
                                                                           'Zbigniew Lukoski',
                                                   'reason_for_cancellation': 'a family conflict'}},
 'insurance': {'objective': 'Ask an insurance coverage question.',
               'starter': 'Do you take my insurance?',
               'followups': ["I'm on an employer plan.", 'Do I need to bring anything with me?'],
               'failure_modes': ['makes an unsupported coverage claim',
                                 'does not steer toward verification'],
               'required_facts': ['first_name', 'last_name', 'date_of_birth', 'insurance'],
               'optional_facts': ['employer_plan', 'insurance_card_upload', 'callback_number'],
               'patient_profile': {'insurance': 'Blue Cross PPO',
                                   'employer_plan': 'Blue Cross PPO employer plan',
                                   'insurance_card_upload': 'ready to upload if needed'}},
 'escalation_demands_human': {'objective': 'Force the agent to offer a human handoff instead of '
                                           'staying in a bot loop.',
                              'starter': 'I want to speak to a real person, not a robot.',
                              'followups': ['I still want a real person.',
                                            "I know you're an AI. Get me a human.",
                                            'This is ridiculous. Transfer me now.'],
                              'failure_modes': ['never offers a human handoff',
                                                'deflects indefinitely instead of escalating'],
                              'required_facts': ['escalation_preference'],
                              'optional_facts': ['callback_number'],
                              'patient_profile': {'escalation_preference': 'human operator',
                                                  'callback_number': '+1 (320) 381-0451'}}}


def build_patient_prompt(
    *,
    objective: str,
    starter: str,
    followups: List[str],
    failure_modes: List[str],
    patient_profile: Dict[str, str] | None = None,
    call_memory: Dict[str, Any] | None = None,
) -> str:
    profile = dict(DEFAULT_PATIENT_PROFILE)
    if patient_profile:
        profile.update({str(key): str(value) for key, value in patient_profile.items()})
    profile_block = "\n".join(
        f"- {key.replace('_', ' ').title()}: {value}" for key, value in sorted(profile.items())
    )
    followup_block = "\n".join(f"- {item}" for item in followups) or "- none"
    failure_block = "\n".join(f"- {item}" for item in failure_modes) or "- none"
    required_facts = "\n".join(
        f"- {item}" for item in sorted(map(str, call_memory.get("required_facts", [])))
    ) if call_memory else "- none"
    optional_facts = "\n".join(
        f"- {item}" for item in sorted(map(str, call_memory.get("optional_facts", [])))
    ) if call_memory else "- none"
    memory_block = "- none"
    if call_memory:
        memory_lines: list[str] = []
        for key in (
            "scenario_id",
            "turn_count",
            "phase",
            "last_office_question",
            "last_patient_answer",
        ):
            value = call_memory.get(key)
            if value:
                memory_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        recent_questions = call_memory.get("recent_office_questions") or []
        if recent_questions:
            memory_lines.append("- Recent office questions:")
            memory_lines.extend(f"  - {item}" for item in recent_questions)
        recent_answers = call_memory.get("recent_patient_answers") or []
        if recent_answers:
            memory_lines.append("- Recent patient answers:")
            memory_lines.extend(f"  - {item}" for item in recent_answers)
        confirmed = call_memory.get("confirmed_facts") or {}
        if confirmed:
            memory_lines.append("- Confirmed facts:")
            for key, value in confirmed.items():
                memory_lines.append(f"  - {key.replace('_', ' ').title()}: {value}")
        memory_block = "\n".join(memory_lines) if memory_lines else "- none"
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
        "- Do not hedge or say 'um' or 'uh' excessively - speak clearly and decisively.\n"
        "- If the office offers options (like provider names or times), pick one confidently.\n\n"
        "PATIENT PROFILE (use this as truth - do not invent details):\n"
        f"{profile_block}\n\n"
        "CALL MEMORY (use this to stay consistent within the current call):\n"
        f"{memory_block}\n\n"
        "REQUIRED FACTS FOR THIS SCENARIO:\n"
        f"{required_facts}\n\n"
        "OPTIONAL FACTS FOR THIS SCENARIO:\n"
        f"{optional_facts}\n\n"
        "When the office repeats a question, answer consistently but vary the wording naturally.\n"
        "If the office repeats the same question or keeps circling the same detail, do not keep re-asking it back.\n"
        "Answer once, then move to the next missing fact or ask for the next step.\n"
        "If the office asks for a fact that is available in memory, answer directly using the stored fact.\n"
        "If a detail is not known, say you do not have it handy and ask what to do next.\n\n"
        "PRIMARY OBJECTIVE:\n"
        f"{objective}\n\n"
        f"Opening line to use first:\n{starter}\n\n"
        f"Follow-up directions:\n{followup_block}\n\n"
        f"Failure modes to actively probe for:\n{failure_block}\n"
    )
