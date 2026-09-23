import sys
import asyncio
import json
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types
from .response_agent import response_generation_agent
from .schema import ExecutionResult

# Ensure UTF-8 output encoding for Windows terminal printing (supports ₹ Rupee symbol)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

# Test Payload 1: Aadhaar Update
aadhaar_payload = ExecutionResult(
    service_name="Aadhaar Address Update",
    document_type="Aadhaar",
    overall_status="ACTION_REQUIRED",
    completed_steps=[
        "Online update form filled",
        "Utility bill (Proof of Address) uploaded"
    ],
    pending_steps=[
        "Biometric re-verification at Aadhaar Seva Kendra",
        "Final approval and URN generation"
    ],
    action_required="Book biometric verification slot at nearest UIDAI Kendra",
    important_details={
        "draft_update_request_number": "URN-9876-5432-1098",
        "deadline": "30 September 2026",
        "fee": "Rs 50 (payable at center)"
    },
    missing_information=[],
    official_references=[
        "https://myaadhaar.uidai.gov.in/"
    ],
    user_language="English"
)

# Test Payload 2: Passport Renewal (Multi-stage)
passport_payload = ExecutionResult(
    service_name="Passport Re-issue (Renewal)",
    document_type="Passport",
    overall_status="IN_PROGRESS",
    completed_steps=[
        "Passport Seva Online application form submitted",
        "Application fee of Rs 1500 paid online",
        "PSK Appointment scheduled"
    ],
    pending_steps=[
        "Physical document verification at Passport Seva Kendra (PSK)",
        "Police verification at local police station",
        "Printing & Speed Post delivery of passport"
    ],
    action_required="Visit PSK Chennai on 15 Oct 2026 at 10:30 AM with original documents",
    important_details={
        "arn_number": "26-1004589231",
        "appointment_date": "15 October 2026",
        "appointment_time": "10:30 AM",
        "venue": "Passport Seva Kendra, Salai Road, Chennai",
        "fee_paid": "Rs 1500"
    },
    missing_information=[
        "Original Old Passport",
        "Self-attested copy of Aadhaar Card"
    ],
    official_references=[
        "https://www.passportindia.gov.in/"
    ],
    user_language="English"
)

# Test Payload 3: Community Certificate (Regional Context)
community_cert_payload = ExecutionResult(
    service_name="Community Certificate Application",
    document_type="Community Certificate",
    overall_status="BLOCKED",
    completed_steps=[
        "e-Sevai portal submission completed",
        "Initial verification by Village Administrative Officer (VAO)"
    ],
    pending_steps=[
        "Field inspection by Revenue Inspector (RI)",
        "Approval by Tahsildar",
        "Digital Certificate Generation"
    ],
    action_required="Upload missing Smart Ration Card copy to unblock application",
    important_details={
        "application_number": "TN-720260923101",
        "submitted_date": "20 September 2026"
    },
    missing_information=[
        "Smart Ration Card / Family Card copy"
    ],
    official_references=[
        "https://tnesevai.tn.gov.in/"
    ],
    user_language="English"
)


async def run_test(payload: ExecutionResult, test_name: str):
    print(f"\n=================== RUNNING TEST: {test_name} ===================")
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            runner = InMemoryRunner(
                agent=response_generation_agent,
                app_name=f"response_gen_{test_name.lower().replace(' ', '_')}"
            )

            session = await runner.session_service.create_session(
                app_name=f"response_gen_{test_name.lower().replace(' ', '_')}",
                user_id="test_user"
            )

            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=payload.model_dump_json()
                    )
                ]
            )

            async for event in runner.run_async(
                user_id="test_user",
                session_id=session.id,
                new_message=message
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            print(part.text)
            break
        except Exception as err:
            if attempt < max_retries:
                print(f"[Warning] Retrying {test_name} in {attempt * 2}s due to temporary API issue: {err}")
                await asyncio.sleep(attempt * 2)
            else:
                print(f"[Error] Failed running {test_name}: {err}")


async def main():
    await run_test(aadhaar_payload, "Aadhaar Update")
    await run_test(passport_payload, "Passport Renewal")
    await run_test(community_cert_payload, "Community Certificate")

if __name__ == "__main__":
    asyncio.run(main())