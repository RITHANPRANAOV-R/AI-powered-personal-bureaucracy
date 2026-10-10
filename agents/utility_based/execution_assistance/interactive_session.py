from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .schema import ConfirmedExecutionContext, ActionExecutionResult, ExecutionOutcome

from .final_review import FinalReviewGate, submission_package

logger = logging.getLogger(__name__)

UIDAI_OFFICIAL_URL = "https://myaadhaar.uidai.gov.in/"
UIDAI_LOGIN_URL = "https://tathya.uidai.gov.in/access/login?role=resident"

# Documented by the citizen from the authenticated MyAadhaar dashboard.
# Require the documented services layout together with origin, checkpoint and session checks.
# Transaction history is a layout section, not a mandatory authentication signal.
DASHBOARD_VERIFIER_VERSION = "services-dashboard-v2"
AUTHENTICATED_DASHBOARD_TEXT = (
    "myAadhaar", "Services", "Address update", "Download Aadhaar",
    "Document update", "Bank seeding status", "Lock/Unlock biometrics",
)


# Read-only recognition reuses controls already targeted by the existing fill helpers.
ADDRESS_REVIEW_CONTROLS = {
    "pincode": 'input[name*="pincode" i], input[name*="pin" i], input[placeholder*="PIN" i], input[placeholder*="Pincode" i], input[id*="pin" i]',
    "house": 'input[name*="house" i], input[name*="flat" i], input[name*="building" i], input[id*="house" i], textarea[name*="house" i]',
    "street": 'input[name*="street" i], input[name*="road" i], input[name*="lane" i], input[id*="street" i]',
    "care_of": 'input[name*="careOf" i], input[name*="co" i], input[placeholder*="Care of" i], input[id*="careOf" i]',
    "landmark": 'input[name*="landmark" i], input[id*="landmark" i]',
    "area": 'input[name*="area" i], input[name*="locality" i], input[name*="sector" i], input[id*="area" i]',
    "vtc": 'select[name*="vtc" i], select[formcontrolname*="vtc" i], select[id*="vtc" i], mat-select[formcontrolname*="vtc" i]',
    "post_office": 'select[name*="postOffice" i], select[formcontrolname*="postOffice" i], select[id*="po" i], mat-select[formcontrolname*="postOffice" i]',
}
# Citizen-documented upload UI; these labels prove page arrival, never file acceptance.
DOCUMENT_PAGE_TEXT = ("Document upload by", "Manual Upload", "Select Valid Supporting Document Type",
                      "Upload supporting document", "Select Supporting Document")


class PortalStage(str, Enum):
    INIT = "init"
    STAGE_1A_OTP = "stage_1a_otp"
    STAGE_1B_LOGIN = "stage_1b_login"
    STAGE_2_SERVICE = "stage_2_service"
    STAGE_3_ADDRESS = "stage_3_address"
    STAGE_4_DOCUMENT = "stage_4_document"
    STAGE_5_REVIEW = "stage_5_review"
    STAGE_6_COMPLETED = "stage_6_completed"


STAGE_DEFINITIONS = [
    {
        "id": PortalStage.STAGE_1A_OTP.value,
        "step_number": 1,
        "title": "Resident Authentication & CAPTCHA",
        "description": "Your 12-digit Aadhaar number is autofilled in Chromium. Please solve the security CAPTCHA in the browser, then click 'Send OTP to Mobile' below.",
        "action_prompt": "Solve CAPTCHA in Chromium, then click 'Send OTP to Mobile'.",
        "button_label": "Send OTP to Mobile",
        "requires_portal_interaction": True,
    },
    {
        "id": PortalStage.STAGE_1B_LOGIN.value,
        "step_number": 2,
        "title": "Enter 6-Digit OTP & Verify Login",
        "description": "Please enter the 6-digit Aadhaar OTP received on your mobile phone in the Chromium window, then click 'Submit OTP & Access Dashboard' below.",
        "action_prompt": "Enter the 6-digit OTP in Chromium, then click 'Submit OTP & Access Dashboard'.",
        "button_label": "Submit OTP & Access Dashboard",
        "requires_portal_interaction": True,
    },
    {
        "id": PortalStage.STAGE_2_SERVICE.value,
        "step_number": 3,
        "title": "Select 'Address Update' Service",
        "description": "The assistant will navigate to 'Address Update' on the official UIDAI portal dashboard.",
        "action_prompt": "Confirm consent to navigate to the demographic address update module.",
        "button_label": "Approve & Navigate to Address Section",
        "requires_portal_interaction": False,
    },
    {
        "id": PortalStage.STAGE_3_ADDRESS.value,
        "step_number": 4,
        "title": "Autofill Verified Address Details",
        "description": "The assistant will populate confirmed address fields, read them back, and verify arrival at the supporting-document page.",
        "action_prompt": "Confirm and submit these verified demographic details to the official form.",
        "button_label": "Approve & Fill Address and Continue",
        "requires_portal_interaction": False,
    },
    {
        "id": PortalStage.STAGE_4_DOCUMENT.value,
        "step_number": 5,
        "title": "Attach Proof of Address Document",
        "description": "Upload your supporting document manually in the official portal. The app checks available evidence and cannot claim acceptance without a verified portal signal.",
        "action_prompt": "Inspect supporting-document status. An unverified upload remains pending.",
        "button_label": "Check Supporting Document Status",
        "requires_portal_interaction": False,
    },
    {
        "id": PortalStage.STAGE_5_REVIEW.value,
        "step_number": 6,
        "title": "Final Review & Official Submission",
        "description": "Final review of demographic details and submission to the UIDAI SSUP registry.",
        "action_prompt": "Confirm final approval to submit your Aadhaar address update.",
        "button_label": "Final Submit & Issue URN",
        "requires_portal_interaction": False,
    },
]


@dataclass
class ActiveBrowserSession:
    session_id: str
    context: ConfirmedExecutionContext
    current_stage: PortalStage = PortalStage.STAGE_1A_OTP
    urn: str = ""
    last_result: ActionExecutionResult | None = None
    last_result_stage: str | None = None
    dashboard_diagnostic: dict | None = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    execution_version: int = 0
    attempts: dict = field(default_factory=dict)
    active_attempt: str | None = None
    execution_uncertain: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    playwright_instance: Any = None
    browser: Any = None
    page: Any = None
    authentication_page: Any = None
    authentication_context: Any = None
    authentication_browser: Any = None
    final_review: FinalReviewGate = field(default_factory=FinalReviewGate)
    supporting_document_result: ActionExecutionResult | None = None
    submission_validation: dict | None = None


def page_observation_reference(session):
    """Public correlation only; never an authorization credential."""
    if session.page is None:
        return None
    if getattr(session, "_observed_page", None) is not session.page:
        session._observed_page = session.page
        session._page_observation_reference = str(uuid4())
    return session._page_observation_reference


class InteractivePortalManager:
    """
    Manages live interactive browser sessions using Playwright where the user
    provides consent and clicks submit in our web application for each official UIDAI update step.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, ActiveBrowserSession] = {}
        self._lock = asyncio.Lock()
        self._attempt_lock = threading.RLock()

    def get_stage_info(self, stage: PortalStage) -> Optional[Dict[str, Any]]:
        for defn in STAGE_DEFINITIONS:
            if defn["id"] == stage.value:
                return defn
        return None

    async def start_session(self, context: ConfirmedExecutionContext, urn: str = "0000/12345/67890") -> Dict[str, Any]:
        from .review_context import review_registry, ReviewError
        if context.review_context is None:
            if any(f.resolution_projection for f in context.facts.values()):
                raise ReviewError("Server-owned review reference is required for resolver projection.")
            return await self._start_session_impl(context, urn)
        context_id = review_registry.reserve_launch(context)
        try:
            result = await self._start_session_impl(context, urn)
            review_registry.finish_launch(context_id, True)
            return result
        except BaseException:
            # Uncertain browser effects must never restore launch permission.
            try:
                review_registry.finish_launch(context_id, False)
            except ReviewError:
                pass
            raise

    def _boundary_lock(self, managed):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def boundary():
            if managed:
                yield  # Registry reservation provides per-context exclusion.
            else:
                async with self._lock:
                    yield
        return boundary()

    async def _start_session_impl(
        self,
        context: ConfirmedExecutionContext,
        urn: str = "0000/12345/67890",
    ) -> Dict[str, Any]:
        async with self._boundary_lock(context.review_context is not None):
            session_id = context.session_id or str(uuid4())
            session = ActiveBrowserSession(
                session_id=session_id,
                context=context,
                current_stage=PortalStage.STAGE_1A_OTP,
                urn=urn,
            )
            self._sessions[session_id] = session

            # Independently validate immediately before dispatch, after manager serialization.
            if context.review_context is not None:
                from .review_context import review_registry
                review_registry.validate(context)
            # Launch Chromium via Playwright & automatically navigate to Login
            await self._launch_and_navigate_login(session)

            stage_info = self.get_stage_info(session.current_stage)
            return {
                "session_id": session_id,
                "status": "active",
                "execution_state_version": session.execution_version,
            "execution_uncertain": session.execution_uncertain,
            "current_stage": session.current_stage.value,
                "stage_info": stage_info,
                "all_stages": STAGE_DEFINITIONS,
                "urn": session.urn if session.current_stage == PortalStage.STAGE_6_COMPLETED else None,
                "message": "Official UIDAI Login page launched in Chromium. Please enter CAPTCHA in the browser, then click 'Send OTP to Mobile' here in the app.",
            }

    def _parse_address_components(self, facts: Dict[str, Any]) -> Dict[str, str]:
        new_addr = str(facts.get("new_address") or facts.get("address") or facts.get("existing_address") or "")
        pincode = str(facts.get("pincode") or "")
        house = str(facts.get("house_no") or facts.get("house") or facts.get("building") or facts.get("flat") or "")
        street = str(facts.get("street") or facts.get("road") or facts.get("lane") or "")
        landmark = str(facts.get("landmark") or "")
        area = str(facts.get("locality") or facts.get("area") or facts.get("sector") or "")
        vtc = str(facts.get("vtc") or facts.get("city") or facts.get("town") or "")
        post_office = str(facts.get("post_office") or facts.get("po") or "")
        care_of = str(facts.get("care_of") or facts.get("guardian") or facts.get("father_name") or facts.get("name") or "")

        import re
        if not pincode and new_addr:
            pins = set(re.findall(r'\b[1-9][0-9]{5}\b', new_addr))
            if len(pins) > 1:
                raise ValueError("Multiple address PIN values require explicit citizen clarification.")
            if pins:
                pincode = next(iter(pins))
        if pincode and re.fullmatch(r"[1-9][0-9]{5}", pincode) is None:
            raise ValueError("Address PIN must be six digits beginning with 1-9.")

        # Remove only an explicit PIN label matching the confirmed PIN; never replace it.
        labelled_pins = re.findall(r"(?:pin\s*code|pincode|postal\s*code)\s*[:=-]\s*([1-9][0-9]{5})(?![0-9])", new_addr, re.I)
        if labelled_pins:
            if not pincode or any(pin != pincode for pin in labelled_pins):
                raise ValueError("Labelled address PIN conflicts with the confirmed PIN; citizen correction is required.")
            new_addr = re.sub(r"(?:pin\s*code|pincode|postal\s*code)\s*[:=-]\s*[1-9][0-9]{5}(?![0-9])", "", new_addr, flags=re.I).rstrip(" ,;- ")

        if not care_of and new_addr:
            m_co = re.search(r'\b(C/O|S/O|W/O|D/O|Care\s+of)\s*[:\-]?\s*([^,\n]+)', new_addr, re.IGNORECASE)
            if m_co:
                care_of = m_co.group(2).strip()

        if not house and new_addr:
            parts = [p.strip() for p in new_addr.split(',') if p.strip()]
            if parts:
                house = parts[0]
                if len(parts) > 1 and not street:
                    street = parts[1]

        return {
            "new_address": new_addr,
            "pincode": pincode,
            "house": house,
            "street": street,
            "landmark": landmark,
            "area": area,
            "vtc": vtc,
            "city": vtc,
            "post_office": post_office,
            "care_of": care_of,
        }

    async def submit_step(self, session_id: str, user_consent: bool, notes: Optional[str] = None,
                          user_inputs: Optional[Dict[str, Any]] = None, *, request_id=None,
                          expected_stage=None, expected_state_version=None) -> Dict[str, Any]:
        from .review_context import review_registry, ReviewError
        context_id = None
        session = self._sessions.get(session_id)
        def blocked(message):
            return {"session_id": session_id, "is_completed": False,
                    "execution_result": ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=message).model_dump(mode="json")}
        if session is None:
            response = blocked("Existing execution session is required.")
            response["execution_result"]["status"] = "NEEDS_USER"
            return response
        # Internal calls (including unchanged Phase 7) use the same reservation.
        internal = request_id is None and expected_stage is None and expected_state_version is None
        with self._attempt_lock, review_registry._lock:
            if session.execution_uncertain or session.active_attempt is not None:
                return blocked("Execution is pending or uncertain; human reconciliation is required.")
            if internal:
                request_id, expected_stage, expected_state_version = str(uuid4()), session.current_stage.value, session.execution_version
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or request_id in session.attempts:
                return blocked("Missing or duplicate execution request identifier.")
            if expected_stage != session.current_stage.value or type(expected_state_version) is not int or expected_state_version != session.execution_version:
                return blocked("Stale execution stage or state version.")
            if len(session.attempts) >= 128:
                return blocked("Execution attempt capacity reached; human reconciliation is required.")
            if session.current_stage == PortalStage.STAGE_5_REVIEW:
                reason = session.final_review.validate(submission_package(session))
                if reason:
                    return blocked(reason)
            try:
                if session.context.review_context is None and any(f.resolution_projection for f in session.context.facts.values()):
                    raise ReviewError("Server-owned review reference is required.")
                if user_inputs:
                    from .context_validator import apply_context_corrections
                    corrected = apply_context_corrections(session.context, user_inputs)
                    if corrected != session.context:
                        session.execution_version += 1
                    session.context = corrected
                    user_inputs = None
                if session.current_stage == PortalStage.STAGE_5_REVIEW:
                    reason = session.final_review.validate(submission_package(session))
                    if reason:
                        raise ReviewError(reason)
                if session.context.review_context is not None:
                    context_id = review_registry.begin_execution(session.context)
            except ValueError as error:
                response = blocked(str(error))
                response.update(request_reserved=False, retry_permitted=True,
                    current_stage=session.current_stage.value, execution_state_version=session.execution_version)
                return response
            attempt = {"stage": expected_stage, "version": session.execution_version, "state": "reserved", "non_dispatch_proven": False, "observation_reference": str(uuid4())}
            session.attempts[request_id] = attempt
            session.active_attempt = request_id
        try:
            previous_diagnostic = session.dashboard_diagnostic
            previous_verification_revision = getattr(session, "verification_revision", 0)
            response = await self._submit_step_impl(session_id, user_consent, notes, user_inputs)
            response["execution_diagnostic"] = {
                "verifier_version": DASHBOARD_VERIFIER_VERSION,
                "stage_verifier": attempt["stage"],
                "page_reference": page_observation_reference(session),
                "attempt_reference": attempt["observation_reference"],
                "input_state_version": attempt["version"],
                "result_origin": "new_attempt",
                "result_category": response.get("execution_result", {}).get("status", "UNKNOWN"),
                "verifier_invoked": session.dashboard_diagnostic is not previous_diagnostic or getattr(session, "verification_revision", 0) != previous_verification_revision,
                "verification_check": getattr(session, "last_verification_kind", None) if getattr(session, "verification_revision", 0) != previous_verification_revision else None,
            }
            with self._attempt_lock:
                success = response.get("execution_result", {}).get("status") == "VERIFIED_SUCCESS"
                if attempt["non_dispatch_proven"]:
                    attempt["state"] = "not_dispatched"
                    response["retry_permitted"] = True
                elif success:
                    attempt["state"] = "verified_success"
                else:
                    attempt["state"] = "uncertain"
                    session.execution_uncertain = True
                    # Preserve observed portal evidence; it does not authorize retry.
                    response["attempt_outcome"] = "uncertain"
                    response["status"] = "unknown"
                    response["message"] = response.get("execution_result", {}).get("message") or "Reserved action outcome is uncertain; human reconciliation is required."
                    response["is_completed"] = False
                    response["retry_permitted"] = False
            return response
        except BaseException:
            with self._attempt_lock:
                attempt["state"] = "uncertain"
                session.execution_uncertain = True
            raise
        finally:
            with self._attempt_lock:
                session.active_attempt = None
                session.execution_version += 1
            if context_id is not None:
                review_registry.end_execution(context_id, uncertain=session.execution_uncertain)
            if 'response' in locals():
                response["execution_state_version"] = session.execution_version
                response["execution_uncertain"] = session.execution_uncertain
                if "execution_diagnostic" in response:
                    response["execution_diagnostic"]["state_version"] = session.execution_version
                    session.last_observation = dict(response["execution_diagnostic"])

    def _mark_dispatch(self, session):
        # No await between reservation validation and this conservative marker.
        with self._attempt_lock:
            if session.active_attempt is None or session.execution_uncertain:
                raise ValueError("Execution reservation is unavailable.")
            if session.context.review_context is not None:
                from .review_context import review_registry
                review_registry.validate(session.context, require_handoff=True)
            session.attempts[session.active_attempt]["state"] = "dispatch_may_have_occurred"

    async def _dispatch_reserved_action(self, session, current):
        if current == PortalStage.STAGE_1A_OTP:
            return await self._dispatch_otp_checkpoint(session, current)
        if current == PortalStage.STAGE_3_ADDRESS:
            readiness = await self._verify_address_form_ready(session)
            if readiness.status != ExecutionOutcome.VERIFIED_SUCCESS:
                return readiness
            facts = {key: fact.value for key, fact in session.context.facts.items()}
            if not (facts.get("house_no") or facts.get("house") or facts.get("building") or facts.get("flat")) or not (facts.get("street") or facts.get("road") or facts.get("lane")):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                    message="Confirm House/Building and Street/Road fields in the app before address filling. A combined address alone does not establish their mapping. No browser action was performed.")
        self._mark_dispatch(session)
        return await self._execute_stage_action_on_portal(session, current)

    async def _dispatch_otp_checkpoint(self, session, current):
        # Read-only verification around the existing, unchanged OTP interaction.
        from urllib.parse import urlparse
        page = session.page
        initial_context = getattr(page, "context", None)
        initial_browser = session.browser
        allowed_hosts = {urlparse(UIDAI_OFFICIAL_URL).hostname, urlparse(UIDAI_LOGIN_URL).hostname}
        try:
            continuity = self._check_authentication_continuity(session)
            if continuity is not None:
                return continuity
            origin = urlparse(page.url)
            if origin.scheme != "https" or origin.hostname not in allowed_hosts:
                return ActionExecutionResult(status=ExecutionOutcome.BLOCKED,
                    message="Send OTP requires the existing official MyAadhaar page.")
            otp = page.locator('input[name="otp"], input[placeholder*="OTP" i], #otp').first
            if await otp.is_visible(timeout=2000):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                    message="The portal already shows OTP entry. Inspect the existing session; no additional OTP request was sent.")
            continuity = self._check_authentication_continuity(session)
            inspected_origin = urlparse(page.url)
            if (continuity is not None or session.page is not page or page.context is not initial_context
                    or session.browser is not initial_browser or inspected_origin.scheme != "https"
                    or inspected_origin.hostname != origin.hostname):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                    message="The login session changed during inspection. Inspect the portal; no OTP action was dispatched.")
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                message="The login checkpoint could not be inspected. Check the existing portal before requesting OTP; no action was dispatched.")
        self._mark_dispatch(session)
        result = await self._execute_stage_action_on_portal(session, current)
        try:
            visible = await otp.is_visible(timeout=2000)
            ready = visible and await otp.is_enabled(timeout=2000)
            continuity = self._check_authentication_continuity(session)
            current_origin = urlparse(page.url)
            if (continuity is None and session.page is page
                    and page.context is initial_context and session.browser is initial_browser
                    and current_origin.scheme == "https" and current_origin.hostname == origin.hostname
                    and ready):
                return ActionExecutionResult(status=ExecutionOutcome.VERIFIED_SUCCESS,
                    message="The official portal has advanced to OTP entry. Enter the OTP manually in the existing browser.",
                    verification_evidence="OTP input changed from not visible to visible and enabled on the unchanged official HTTPS UIDAI login origin and browser session.")
        except Exception:
            pass
        if isinstance(result, ActionExecutionResult) and result.status == ExecutionOutcome.FAILED and result.verification_evidence:
            return result
        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
            message="OTP request could not be verified. Inspect the existing UIDAI window for a CAPTCHA error or OTP entry. Do not request another OTP automatically; human reconciliation is required.")

    async def _submit_step_impl(
        self,
        session_id: str,
        user_consent: bool,
        notes: Optional[str] = None,
        user_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        bound_session = self._sessions.get(session_id)
        async with self._boundary_lock(bound_session is not None and bound_session.active_attempt is not None):
            session = self._sessions.get(session_id)
            if not session:
                result = ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser session is missing. Start a new human-controlled login session.")
                return {"session_id": session_id, "status": "needs_user", "is_completed": False,
                        "execution_result": result.model_dump(mode="json"), "message": result.message}

            # OTP belongs in the human-controlled portal, never response history.
            if user_inputs:
                user_inputs = {k: v for k, v in user_inputs.items() if "otp" not in k.casefold()}
            # Merge any user-provided quick corrections / missing inputs
            if user_inputs:
                from .context_validator import apply_context_corrections
                try:
                    session.context = apply_context_corrections(session.context, user_inputs)
                except ValueError as error:
                    result = ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=str(error))
                    return {**self.get_session_status(session_id), "status": "blocked",
                            "is_completed": False, "message": result.message,
                            "execution_result": result.model_dump(mode="json")}

            if not user_consent:
                session.attempts[session.active_attempt]["non_dispatch_proven"] = True
                return {
                    "session_id": session_id,
                    "status": "waiting_for_consent",
                    "execution_state_version": session.execution_version,
            "execution_uncertain": session.execution_uncertain,
            "current_stage": session.current_stage.value,
                    "stage_info": self.get_stage_info(session.current_stage),
                    "message": "Step not executed: User consent is required to proceed with this submission.",
                    "is_completed": False,
                    "execution_result": ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Citizen consent is required.").model_dump(mode="json"),
                }

            current = session.current_stage
            session.history.append({
                "stage": current.value,
                "consent_at": datetime.now(timezone.utc).isoformat(),
                "notes": None if current in {PortalStage.STAGE_1A_OTP, PortalStage.STAGE_1B_LOGIN} else notes,
                "user_inputs": user_inputs,
            })

            if session.context.review_context is not None:
                from .review_context import review_registry
                review_registry.validate(session.context, require_handoff=True)
            # Execute the browser action on the live page
            if current == PortalStage.STAGE_6_COMPLETED:
                return self.get_session_status(session_id)
            try:
                if current == PortalStage.STAGE_2_SERVICE:
                    continuity = self._check_authentication_continuity(session)
                    if continuity is not None:
                        result = continuity
                    else:
                        result = await self._verify_authentication(session)
                        if result.status == ExecutionOutcome.VERIFIED_SUCCESS:
                            continuity = self._check_authentication_continuity(session)
                            result = continuity if continuity is not None else await self._dispatch_reserved_action(session, current)
                else:
                    result = await self._dispatch_reserved_action(session, current)
                if session.attempts[session.active_attempt]["state"] == "reserved":
                    session.attempts[session.active_attempt]["non_dispatch_proven"] = True
                if not isinstance(result, ActionExecutionResult):
                    result = ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Portal outcome was not verified.")
                else:
                    result = ActionExecutionResult.model_validate(result.model_dump())
            except Exception:
                result = ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Portal action raised an exception; the external outcome is unverified and the stage remains pending.")
            if current == PortalStage.STAGE_5_REVIEW and result.status == ExecutionOutcome.VERIFIED_SUCCESS and not result.official_reference:
                result = ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Official submission receipt/reference has not been verified.")
            if current == PortalStage.STAGE_4_DOCUMENT and result.status == ExecutionOutcome.VERIFIED_SUCCESS:
                session.supporting_document_result = result.model_copy(deep=True)
            session.last_result = result
            session.last_result_stage = current.value
            if result.status != ExecutionOutcome.VERIFIED_SUCCESS:
                return {
                    **self.get_session_status(session_id),
                    "status": result.status.value.lower(),
                    "execution_result": result.model_dump(mode="json"),
                    "message": result.message,
                    "is_completed": False,
                }

            # Advance stage
            if current == PortalStage.STAGE_1A_OTP:
                session.current_stage = PortalStage.STAGE_1B_LOGIN
                msg = "OTP requested on official portal. Please enter the 6-digit OTP in the Chromium window, then click 'Submit OTP & Access Dashboard'."
            elif current == PortalStage.STAGE_1B_LOGIN:
                session.current_stage = PortalStage.STAGE_2_SERVICE
                msg = "Login verified on official portal. Ready to navigate to Address Update module."
            elif current == PortalStage.STAGE_2_SERVICE:
                session.current_stage = PortalStage.STAGE_3_ADDRESS
                msg = "Navigated to Address Section on UIDAI. Ready to populate verified address details."
            elif current == PortalStage.STAGE_3_ADDRESS:
                session.current_stage = PortalStage.STAGE_4_DOCUMENT
                msg = "Address details submitted to official form. Ready to attach Proof of Address document."
            elif current == PortalStage.STAGE_4_DOCUMENT:
                session.current_stage = PortalStage.STAGE_5_REVIEW
                msg = "Supporting document selected. Ready for final review & submission."
            elif current == PortalStage.STAGE_5_REVIEW:
                session.current_stage = PortalStage.STAGE_6_COMPLETED
                session.urn = result.official_reference
                msg = f"Aadhaar Address Update submitted successfully to UIDAI! URN: {session.urn}"
            else:
                msg = "Process already completed."

            is_completed = session.current_stage == PortalStage.STAGE_6_COMPLETED
            stage_info = self.get_stage_info(session.current_stage) if not is_completed else None

            return {
                "session_id": session_id,
                "status": "completed" if is_completed else "active",
                "execution_state_version": session.execution_version,
            "execution_uncertain": session.execution_uncertain,
            "current_stage": session.current_stage.value,
                "stage_info": stage_info,
                "all_stages": STAGE_DEFINITIONS,
                "urn": session.urn if session.current_stage == PortalStage.STAGE_6_COMPLETED else None,
                "message": msg,
                "completed_stage": current.value,
                "is_completed": is_completed,
                "execution_result": session.last_result.model_dump(mode="json") if session.last_result else None,
            }

    async def review_submission(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"execution_result": ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Existing browser session is required.").model_dump(mode="json")}
            return {"final_review": session.final_review.view(submission_package(session))}

    async def final_review_action(self, session_id: str, action: str, reviewed_binding: str | None = None) -> Dict[str, Any]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return {"execution_result": ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Existing browser session is required.").model_dump(mode="json")}
            if action in {"Edit / Correct", "Cancel"}:
                session.final_review.invalidate()
                return {"final_review": session.final_review.as_dict(), "execution_result": ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Final approval invalidated; no submission was attempted.").model_dump(mode="json")}
            reason = session.final_review.approve(submission_package(session), reviewed_binding, action)
            if session.current_stage != PortalStage.STAGE_5_REVIEW:
                session.final_review.invalidate()
                reason = "The document stage must be verified before final submission."
            if reason:
                return {"final_review": session.final_review.as_dict(), "execution_result": ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=reason).model_dump(mode="json")}
        return await self.submit_step(session_id, user_consent=True)

    async def _validate_final_submission(self, session: ActiveBrowserSession) -> ActionExecutionResult | None:
        if session.current_stage != PortalStage.STAGE_5_REVIEW:
            return ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message="Final submission is not the current execution stage.")
        reason = session.final_review.validate(submission_package(session))
        if reason:
            return ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=reason)
        if (session.authentication_page is None or session.authentication_context is None
                or session.authentication_browser is None):
            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Established authenticated browser session is required.")
        continuity = self._check_authentication_continuity(session)
        if continuity is not None:
            return continuity
        authentication = await self._verify_authentication(session)
        if authentication.status != ExecutionOutcome.VERIFIED_SUCCESS:
            return authentication
        continuity = self._check_authentication_continuity(session)
        if continuity is not None:
            return continuity
        reason = session.final_review.validate(submission_package(session))
        return ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=reason) if reason else None

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"session_id": session_id, "status": "not_found"}
        is_completed = session.current_stage == PortalStage.STAGE_6_COMPLETED
        return {
            "session_id": session_id,
            "status": "completed" if is_completed else "active",
            "execution_state_version": session.execution_version,
            "execution_uncertain": session.execution_uncertain,
            "current_stage": session.current_stage.value,
            "stage_info": self.get_stage_info(session.current_stage) if not is_completed else None,
            "all_stages": STAGE_DEFINITIONS,
            "urn": session.urn if session.current_stage == PortalStage.STAGE_6_COMPLETED else None,
            "is_completed": is_completed,
            "execution_diagnostic": {
                **getattr(session, "last_observation", {}),
                "verifier_version": DASHBOARD_VERIFIER_VERSION,
                "stage_verifier": session.last_result_stage,
                "result_origin": "retained" if session.last_result else "none",
                "result_category": session.last_result.status.value if session.last_result else "NONE",
                "verifier_invoked": False,
            },
            "history": session.history,
            "execution_result": session.last_result.model_dump(mode="json") if session.last_result else None,
        }

    async def _launch_and_navigate_login(self, session: ActiveBrowserSession) -> None:
        try:
            from playwright.async_api import async_playwright

            chrome_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/usr/bin/brave-browser",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            ]
            browser_binary = next((p for p in chrome_paths if os.path.exists(p) and os.access(p, os.X_OK)), None)

            p = await async_playwright().start()
            session.playwright_instance = p

            launch_kwargs: Dict[str, Any] = {
                "headless": False,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--start-maximized",
                ],
            }
            if browser_binary:
                launch_kwargs["executable_path"] = browser_binary

            browser = await p.chromium.launch(**launch_kwargs)
            session.browser = browser

            # Create a clean browser context to prevent stale session cookies
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            # Mask automation flags to prevent Cloudflare/WAF session rejection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.navigator.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            session.page = page

            origin_url = "https://myaadhaar.uidai.gov.in/"
            login_url = "https://myaadhaar.uidai.gov.in/login"
            fallback_login_url = "https://tathya.uidai.gov.in/access/login?role=resident"

            logger.info(f"Navigating to UIDAI origin ({origin_url}) to initialize session cookies...")
            try:
                await page.goto(origin_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_e:
                logger.debug(f"Origin navigation note: {nav_e}")

            await page.wait_for_timeout(1000)

            # Navigate directly to Resident Login page (working Phase 1 execution path)
            logger.info(f"Navigating directly to UIDAI Resident Login page: {login_url}")
            try:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as login_nav_err:
                logger.debug(f"Direct /login navigation note: {login_nav_err}")

            await page.wait_for_timeout(1000)

            uid_selectors = [
                'input[name="uid"]',
                'input[placeholder*="Aadhaar" i]',
                'input[placeholder*="UID" i]',
                '#uid',
                'input[formcontrolname="uid"]',
                'input[name="aadhaarNum"]',
                'input[type="text"][maxlength="12"]',
                'input[type="text"][maxlength="14"]',
            ]

            # Verify if Resident Login page is visible
            is_on_login_page = False
            for sel in uid_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        is_on_login_page = True
                        break
                except Exception:
                    pass

            if not is_on_login_page:
                logger.info("Not on resident login form yet. Attempting smart click or fallback navigation...")
                await self._smart_click_or_submit(
                    page,
                    target_texts=["Login", "Login with OTP"],
                    selectors=['button:has-text("Login")', 'a[href*="login"]', 'text=Login', 'button:has-text("Login with OTP")'],
                )
                await page.wait_for_timeout(1500)

                for sel in uid_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            is_on_login_page = True
                            break
                    except Exception:
                        pass

                if not is_on_login_page:
                    logger.info(f"Navigating directly to resident login endpoint: {fallback_login_url}")
                    try:
                        await page.goto(fallback_login_url, wait_until="domcontentloaded", timeout=25000)
                    except Exception as goto_err:
                        logger.warning(f"Fallback login navigation note: {goto_err}")

            if len(context.pages) > 1:
                page = context.pages[-1]
                session.page = page
                await page.bring_to_front()

            # Verify Resident Login field is visible before continuing to autofill
            logger.info("Waiting for Aadhaar UID input field on Resident Login page...")
            try:
                await page.wait_for_selector(
                    'input[name="uid"], input[placeholder*="Aadhaar" i], input[placeholder*="UID" i], #uid, input[type="text"]',
                    timeout=20000,
                    state="visible",
                )
            except Exception as wait_uid_err:
                logger.warning(f"UID wait_for_selector notice: {wait_uid_err}")

            # Autofill Aadhaar number strictly from confirmed context (NO hardcoded/demo fallback)
            try:
                def extract_fact_val(v: Any) -> str:
                    if hasattr(v, "value"):
                        return str(v.value or "")
                    if isinstance(v, dict):
                        return str(v.get("value") or "")
                    return str(v or "")

                facts = {k: extract_fact_val(v) for k, v in session.context.facts.items()}
                aadhaar_num = (
                    facts.get("aadhaar_number")
                    or facts.get("aadhaar")
                    or facts.get("uid")
                    or ""
                )
                clean_aadhaar = "".join(filter(str.isdigit, str(aadhaar_num)))

                if len(clean_aadhaar) == 12:
                    filled = False
                    for sel in uid_selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() > 0 and await loc.is_visible():
                                await loc.scroll_into_view_if_needed()
                                await loc.click()
                                await page.keyboard.press("Control+A")
                                await page.keyboard.press("Backspace")
                                await loc.press_sequentially(clean_aadhaar, delay=35)

                                # Synchronize React internal fiber / synthetic state
                                await page.evaluate("""
                                    ([sel, val]) => {
                                        const el = document.querySelector(sel);
                                        if (el) {
                                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                            if (nativeSetter) {
                                                nativeSetter.call(el, val);
                                            } else {
                                                el.value = val;
                                            }
                                            el.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                                            el.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                                            el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: val.slice(-1) }));
                                        }
                                    }
                                """, [sel, clean_aadhaar])

                                await page.keyboard.press("Tab")
                                filled = True
                                logger.info(f"Successfully autofilled confirmed Aadhaar UID ({clean_aadhaar[:4]}****{clean_aadhaar[-4:]}) into resident login portal via selector '{sel}'.")
                                break
                        except Exception as try_fill_err:
                            logger.debug(f"UID fill attempt on '{sel}' failed: {try_fill_err}")
                            continue
                else:
                    logger.warning(
                        f"No valid 12-digit confirmed Aadhaar number found in context (raw value: '{aadhaar_num}'). "
                        "Autofill skipped without hardcoded fallback."
                    )

                # Focus on the CAPTCHA field so the user can immediately type
                captcha_selectors = [
                    'input[name="captcha"]',
                    'input[placeholder*="Captcha" i]',
                    'input[placeholder*="CAPTCHA" i]',
                    '#captcha',
                    'input[formcontrolname="captcha"]',
                ]
                for cap_sel in captcha_selectors:
                    try:
                        cap_loc = page.locator(cap_sel).first
                        if await cap_loc.count() > 0 and await cap_loc.is_visible():
                            await cap_loc.focus()
                            break
                    except Exception:
                        pass
            except Exception as autofill_err:
                logger.warning(f"Aadhaar login autofill warning: {autofill_err}")

        except Exception as error:
            logger.warning(f"Error during Playwright launch/navigation: {error}")
            if not session.browser:
                self._fallback_open_browser()

    def _check_authentication_continuity(self, session: ActiveBrowserSession) -> ActionExecutionResult | None:
        """Object identity is continuity evidence, not authentication evidence."""
        try:
            if self._sessions.get(session.session_id) is not session:
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser session was replaced. Human authentication is required.")
            if session.page is None:
                return ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message="Browser page is unavailable.")
            closed = session.page.is_closed()
            if closed is not True and closed is not False:
                return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Browser page state cannot be determined.")
            if closed:
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser page is closed. Human authentication is required.")
            context = session.page.context
            if context is None:
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser context is unavailable. Human authentication is required.")
            if session.page not in context.pages:
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser page no longer belongs to its session context.")
            if session.browser is None or context.browser is not session.browser or not session.browser.is_connected():
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="Browser connection or context was lost. Human authentication is required.")
            if session.authentication_page is not None and (
                session.page is not session.authentication_page
                or context is not session.authentication_context
                or session.browser is not session.authentication_browser
            ):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="OTP browser page or context was replaced. Human authentication is required.")
            if session.current_stage == PortalStage.STAGE_2_SERVICE and session.authentication_page is None:
                return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="No continuous OTP authentication session can be verified.")
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Browser session continuity cannot be determined.")
        return None

    async def _login_checkpoint_visible(self, page: Any) -> bool:
        # Reuse the OTP and UID selectors from the existing resident-login implementation.
        if await page.locator('input[name="otp"], input[placeholder*="OTP" i], #otp').first.is_visible(timeout=2000):
            return True
        inputs = page.locator('input[name="uid"], input[placeholder*="Aadhaar" i], input[placeholder*="UID" i], #uid, input[formcontrolname="uid"], input[name="aadhaarNum"], input[type="text"][maxlength="12"], input[type="text"][maxlength="14"]')
        for index in range(await inputs.count()):
            if await inputs.nth(index).is_visible(timeout=2000):
                return True
        return False

    async def _verify_authentication(self, session: ActiveBrowserSession) -> ActionExecutionResult:
        result = await self._inspect_authentication(session)
        # Only fixed implementation identity and outcome category; never portal text or citizen data.
        session.dashboard_diagnostic = {"verifier_version": DASHBOARD_VERIFIER_VERSION,
                                        "result_category": result.status.value}
        logger.info("Dashboard verifier=%s category=%s origin=new_verification",
                    DASHBOARD_VERIFIER_VERSION, result.status.value)
        return result

    async def _inspect_authentication(self, session: ActiveBrowserSession) -> ActionExecutionResult:
        """Read-only inspection of the citizen-documented authenticated dashboard."""
        import re
        from urllib.parse import urlsplit

        continuity = self._check_authentication_continuity(session)
        if continuity is not None:
            return continuity
        try:
            page = session.page
            origin = urlsplit(page.url)
            if origin.scheme != "https" or origin.hostname not in {"myaadhaar.uidai.gov.in", "tathya.uidai.gov.in"}:
                return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Authentication cannot be verified on this page.")
            # Body is standard HTML, not an invented UIDAI-specific error selector.
            # Raw portal text is never returned or logged.
            visible_text = await page.locator("body").inner_text(timeout=2000)
            continuity = self._check_authentication_continuity(session)
            if continuity is not None:
                return continuity
            if re.search(r"\b(?:expired\s+otp|otp\s+(?:has\s+)?expired)\b", visible_text, re.IGNORECASE):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="The portal reports an expired OTP. Complete the human-controlled OTP checkpoint again.")
            if re.search(r"\b(?:(?:invalid|incorrect)\s+otp|otp\s+(?:is\s+)?(?:invalid|incorrect)|authentication\s+failed|authentication\s+failure)\b", visible_text, re.IGNORECASE):
                return ActionExecutionResult(status=ExecutionOutcome.FAILED, message="The portal reports unsuccessful OTP authentication. Human correction is required.")
            if await self._login_checkpoint_visible(page):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="The OTP/resident login checkpoint is still visible. Authentication is not verified.")
            if origin.hostname == "myaadhaar.uidai.gov.in":
                for label in AUTHENTICATED_DASHBOARD_TEXT:
                    # Text comes from the documented page, not a guessed DOM selector.
                    # The captured dashboard renders "Lock / Unlock biometrics".
                    # Normalize separator whitespace without changing the required words.
                    words = r"\s+".join(re.escape(word) for word in label.split())
                    words = words.replace("/", r"\s*/\s*")
                    text = re.compile(r"^\s*" + words + r"\s*$", re.IGNORECASE)
                    matches = page.get_by_text(text)
                    visible = False
                    for index in range(await matches.count()):
                        if await matches.nth(index).is_visible(timeout=2000):
                            visible = True
                            break
                    if not visible:
                        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                            message=f"Dashboard access is not verified: the documented '{label}' section is not visible. Inspect the existing portal; do not repeat OTP submission automatically.")
                continuity = self._check_authentication_continuity(session)
                if continuity is not None:
                    return continuity
                if await self._login_checkpoint_visible(page):
                    return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="The login checkpoint reappeared. Human authentication is required.")
                continuity = self._check_authentication_continuity(session)
                if continuity is not None:
                    return continuity
                current_origin = urlsplit(page.url)
                if current_origin.scheme != "https" or current_origin.hostname != "myaadhaar.uidai.gov.in":
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="The page changed during authentication inspection.")
                return ActionExecutionResult(
                    status=ExecutionOutcome.VERIFIED_SUCCESS,
                    message="Authenticated MyAadhaar dashboard verified in the OTP browser session.",
                    verification_evidence="Observed official HTTPS MyAadhaar origin, visible myAadhaar header, Services heading and all five documented services-layout card labels, no visible OTP/resident-login controls, and unchanged OTP page/browser context.",
                )
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Authentication state cannot be determined from the browser page.")
        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="The documented authenticated MyAadhaar dashboard cannot be verified on this page.")

    async def _service_page_guard(self, session):
        from urllib.parse import urlsplit
        continuity = self._check_authentication_continuity(session)
        if continuity is not None:
            return continuity
        if session.authentication_page is None:
            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="An established authenticated browser session is required.")
        origin = urlsplit(session.page.url)
        if origin.scheme != "https" or origin.hostname != "myaadhaar.uidai.gov.in":
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Service state cannot be verified outside the official HTTPS MyAadhaar origin.")
        if await self._login_checkpoint_visible(session.page):
            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER, message="The login checkpoint is visible; service access is not verified.")
        continuity = self._check_authentication_continuity(session)
        if continuity is not None:
            return continuity
        origin = urlsplit(session.page.url)
        if origin.scheme != "https" or origin.hostname != "myaadhaar.uidai.gov.in":
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="The official page changed during service inspection.")
        return None

    async def _visible_control(self, page, selector):
        matches = page.locator(selector)
        visible = []
        for index in range(await matches.count()):
            control = matches.nth(index)
            if await control.is_visible(timeout=2000) and await control.is_enabled(timeout=2000):
                visible.append(control)
        # Disabled display copies are not candidates for filling/readback.
        # Multiple visible enabled controls still make the target ambiguous.
        return visible[0] if len(visible) == 1 else None

    async def _verify_address_destination(self, session):
        """Verify page arrival independently of editable-field readiness."""
        session.verification_revision = getattr(session, "verification_revision", 0) + 1
        session.last_verification_kind = "address_destination"
        import re
        from urllib.parse import urlsplit
        try:
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            page = session.page
            observed_path = "/ssup/demoUpdate/update/en_IN"
            if urlsplit(page.url).path.rstrip("/") == observed_path:
                for label in ("Update Aadhaar Online", "Current Details", "Details to be Updated"):
                    pattern = re.compile(r"^\s*" + r"\s+".join(re.escape(word) for word in label.split()) + r"\s*$", re.I)
                    matches = page.get_by_text(pattern)
                    visible = False
                    for observation in range(8):
                        matches = page.get_by_text(pattern)
                        guard = await self._service_page_guard(session)
                        if guard is not None:
                            return guard
                        for index in range(await matches.count()):
                            if await matches.nth(index).is_visible(timeout=2000):
                                visible = True
                                break
                        if visible:
                            break
                        if observation < 7:
                            await page.wait_for_timeout(250)
                    if not visible:
                        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                            message=f"Address-update destination is not yet verified: '{label}' is not visible. The page may be loading; inspect without repeating navigation.")
                guard = await self._service_page_guard(session)
                if guard is not None:
                    return guard
                if urlsplit(page.url).path.rstrip("/") != observed_path:
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                        message="The destination changed during inspection; navigation remains unverified.")
                return ActionExecutionResult(status=ExecutionOutcome.VERIFIED_SUCCESS,
                    message="Official address-update destination verified. Editable form readiness and address values must still be checked before continuing.",
                    verification_evidence="Fresh observation of the documented address-update path and visible Update Aadhaar Online, Current Details and Details to be Updated labels, on the unchanged official authenticated session without a login checkpoint. This verifies page arrival only.")
            # Preserve the existing positive complete-form evidence for other layouts.
            return await self._verify_address_form_ready(session, require_selection_controls=True)
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                message="Address-update destination could not be inspected; do not repeat navigation automatically.")

    async def _verify_address_form_ready(self, session, *, require_selection_controls=False):
        session.verification_revision = getattr(session, "verification_revision", 0) + 1
        session.last_verification_kind = "address_form_readiness"
        try:
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            fields = ("pincode", "house", "street", "vtc", "post_office") if require_selection_controls else ("pincode", "house", "street")
            for field in fields:
                selector = ADDRESS_REVIEW_CONTROLS[field]
                control = await self._visible_control(session.page, selector)
                if control is None or not await control.is_enabled(timeout=2000):
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                        message=f"Address form is not ready: a unique visible, enabled {field} control was not found. Inspect the existing portal; do not repeat navigation automatically.")
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            return ActionExecutionResult(status=ExecutionOutcome.VERIFIED_SUCCESS,
                message="The official address form is ready in the authenticated browser session.",
                verification_evidence="Fresh observation of the required unique visible enabled address controls on official HTTPS MyAadhaar with no login checkpoint and unchanged authenticated session. Dependent selections are validated separately after PIN filling.")
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Address-form controls could not be inspected. Human inspection is required; navigation must not be repeated automatically.")

    async def _verify_address_values(self, session, expected, validation):
        session.verification_revision = getattr(session, "verification_revision", 0) + 1
        session.last_verification_kind = "address_values"
        try:
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            if not all(validation.get(key) for key in ("pin_valid", "vtc_selected", "po_selected")):
                return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                    message="Address form is incomplete: inspect PIN, Village/Town/City and Post Office. No Next action was performed.")
            for field in ("pincode", "house", "street", "care_of", "landmark", "area"):
                if not expected.get(field):
                    continue
                control = await self._visible_control(session.page, ADDRESS_REVIEW_CONTROLS[field])
                if control is None:
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message=f"The populated {field} control cannot be read back; no Next action was performed.")
                actual = await control.input_value(timeout=2000)
                if " ".join(actual.split()) != " ".join(str(expected[field]).split()):
                    return ActionExecutionResult(status=ExecutionOutcome.FAILED,
                        message=f"The portal {field} value does not match the confirmed input. No Next action was performed.",
                        verification_evidence="Fresh visible form-control readback differs from the intended confirmed field; values are not included in this diagnostic.")
            for field, key in (("vtc", "vtc_val"), ("post_office", "po_val")):
                if expected.get(field) and " ".join(str(validation.get(key, "")).casefold().split()) != " ".join(str(expected[field]).casefold().split()):
                    return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                        message=f"The selected {field} does not match the confirmed value. No Next action was performed.")
            return await self._service_page_guard(session)
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Address values could not be verified; no Next action was performed.")

    async def _verify_document_destination(self, session):
        session.verification_revision = getattr(session, "verification_revision", 0) + 1
        session.last_verification_kind = "document_destination"
        import re
        try:
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            for label in DOCUMENT_PAGE_TEXT:
                pattern = re.compile(r"^\s*" + r"\s+".join(re.escape(word) for word in label.split()) + r"\s*$", re.I)
                matches = session.page.get_by_text(pattern)
                visible = False
                for index in range(await matches.count()):
                    if await matches.nth(index).is_visible(timeout=2000):
                        visible = True
                        break
                if not visible:
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                        message=f"Address progression is unverified: the document-page '{label}' indicator is missing. Inspect the existing portal; do not repeat the action automatically.")
            guard = await self._service_page_guard(session)
            if guard is not None:
                return guard
            return ActionExecutionResult(status=ExecutionOutcome.VERIFIED_SUCCESS,
                message="Verified address values progressed to the official supporting-document page; document acceptance is not yet verified.",
                verification_evidence="Confirmed address readback and mandatory selections before Next, followed by fresh visibility of all five documented upload-page labels in the unchanged official authenticated session.")
        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Document-page arrival could not be inspected; address progression remains unverified.")

    async def _execute_stage_action_on_portal(self, session: ActiveBrowserSession, stage: PortalStage) -> ActionExecutionResult:
        page = session.page
        if not page:
            return ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message="Browser page is unavailable.")

        try:
            facts = {k: v.value for k, v in session.context.facts.items()}
            new_addr = facts.get("new_address") or facts.get("existing_address") or facts.get("address") or ""
            pincode = facts.get("pincode") or ""

            if stage == PortalStage.STAGE_1A_OTP:
                # User clicked "Send OTP to Mobile" in app:
                target_otp_buttons = [
                    "Login with OTP",
                    "Send OTP",
                    "Get OTP",
                ]
                await self._smart_click_or_submit(
                    page,
                    target_texts=target_otp_buttons,
                    selectors=[
                        'button:has-text("Login with OTP")',
                        'button:has-text("Send OTP")',
                        'button[type="submit"]',
                    ],
                )
                logger.info("Executed Send OTP action on UIDAI login portal.")
                await page.wait_for_timeout(1000)
                try:
                    otp_loc = page.locator('input[name="otp"], input[placeholder*="OTP" i], #otp').first
                    if await otp_loc.count() > 0:
                        await otp_loc.focus()
                except Exception:
                    pass

            elif stage == PortalStage.STAGE_1B_LOGIN:
                continuity = self._check_authentication_continuity(session)
                if continuity is not None:
                    return continuity
                if session.authentication_page is None:
                    session.authentication_page = page
                    session.authentication_context = page.context
                    session.authentication_browser = session.browser
                # User entered OTP in Chromium and clicked "Submit OTP & Access Dashboard" in app:
                target_login_buttons = [
                    "Login",
                    "Verify OTP",
                    "Verify & Proceed",
                    "Verify",
                    "Submit",
                ]
                await self._smart_click_or_submit(
                    page,
                    target_texts=target_login_buttons,
                    selectors=[
                        'button:has-text("Login")',
                        'button:has-text("Verify")',
                        'button:has-text("Submit")',
                        'button[type="submit"]',
                    ],
                )
                logger.info("Executed Login/Verify OTP action on UIDAI authentication page.")
                await page.wait_for_timeout(2500)
                result = await self._verify_authentication(session)
                continuity = self._check_authentication_continuity(session)
                return continuity if continuity is not None else result

            elif stage == PortalStage.STAGE_2_SERVICE:
                # User clicked "Approve & Navigate to Address Section" in app:
                # 1. Click Address Update card on dashboard (strictly ignoring Lock/Unlock Biometrics, etc.)
                clicked_address = False
                try:
                    clicked_address = await page.evaluate("""
                        () => {
                            const candidates = Array.from(document.querySelectorAll('a, button, div, span, h3, h4, p'));
                            for (const el of candidates) {
                                const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                const hasAddress = txt.includes('address update') || txt.includes('update address') || txt.includes('update aadhaar online');
                                const isBlacklisted = txt.includes('biometric') || txt.includes('lock') || txt.includes('bank') || txt.includes('pvc') || txt.includes('download');
                                if (hasAddress && !isBlacklisted && el.offsetParent !== null) {
                                    const clickable = el.closest('a') || el.closest('button') || el.closest('div.card') || el.closest('div[role="button"]') || el;
                                    clickable.scrollIntoView();
                                    clickable.click();
                                    clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                except Exception as js_err:
                    logger.debug(f"JS address card click note: {js_err}")

                if not clicked_address:
                    address_selectors = [
                        'a[href*="address-update"]',
                        'a[href*="/address"]',
                        'a[href*="ssup"]',
                        'button:has-text("Address Update")',
                        'div:has-text("Address Update"):not(:has-text("Biometric")):not(:has-text("Lock"))',
                    ]
                    for sel in address_selectors:
                        try:
                            loc = page.locator(sel).first
                            if await loc.count() > 0:
                                await loc.scroll_into_view_if_needed()
                                await loc.click(force=True, timeout=2000)
                                clicked_address = True
                                break
                        except Exception:
                            continue

                await page.wait_for_timeout(1500)

                # 2. On Update options page: click "Update Aadhaar Online"
                try:
                    await self._smart_click_or_submit(
                        page,
                        target_texts=["Update Aadhaar Online", "Update Address (Online)", "Update Address"],
                        selectors=[
                            'a:has-text("Update Aadhaar Online")',
                            'div:has-text("Update Aadhaar Online")',
                            'a:has-text("Update Address (Online)")',
                        ],
                    )
                except Exception as sub_opt_err:
                    logger.debug(f"Update online option click note: {sub_opt_err}")

                await page.wait_for_timeout(1000)

                # 3. Click "Proceed to Update Aadhaar"
                try:
                    await self._smart_click_or_submit(
                        page,
                        target_texts=["Proceed to Update Aadhaar", "Proceed", "Next"],
                        selectors=[
                            'button:has-text("Proceed to Update Aadhaar")',
                            'button:has-text("Proceed")',
                        ],
                    )
                except Exception as proc_err:
                    logger.debug(f"Proceed click note: {proc_err}")

                await page.wait_for_timeout(1500)

                # 4. On demographic field selection screen: Select "Address" checkbox/card
                try:
                    await page.evaluate("""
                        () => {
                            const labels = Array.from(document.querySelectorAll('label, div, span, p'));
                            for (const el of labels) {
                                const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                                if (txt === 'address' || txt.includes('address (')) {
                                    const parent = el.closest('div.card') || el.closest('div[role="button"]') || el.closest('label') || el;
                                    parent.scrollIntoView();
                                    parent.click();
                                    const cb = parent.querySelector('input[type="checkbox"]');
                                    if (cb && !cb.checked) {
                                        cb.checked = true;
                                        cb.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    return true;
                                }
                            }
                            return false;
                        }
                    """)
                except Exception as addr_sel_err:
                    logger.debug(f"Address field checkbox selection note: {addr_sel_err}")

                await page.wait_for_timeout(1000)

                # 5. Click the extra submit button: "Proceed to Update Aadhaar" / "Proceed" / "Submit"
                try:
                    await self._smart_click_or_submit(
                        page,
                        target_texts=["Proceed to Update Aadhaar", "Proceed", "Submit", "Next"],
                        selectors=[
                            'button:has-text("Proceed to Update Aadhaar")',
                            'button:has-text("Proceed")',
                            'button[type="submit"]',
                        ],
                    )
                except Exception as final_proc_err:
                    logger.debug(f"Final proceed to form click note: {final_proc_err}")

                logger.info("Address service navigation actions attempted; inspecting destination.")
                return await self._verify_address_destination(session)

            elif stage == PortalStage.STAGE_3_ADDRESS:
                # User clicked "Approve & Submit Address Details" in app:
                # 1. If still on the field selection screen, ensure "Address" and "Proceed" are clicked
                try:
                    await page.evaluate("""
                        () => {
                            const btn = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('Proceed to Update Aadhaar'));
                            if (btn && btn.offsetParent !== null) {
                                const addrCard = Array.from(document.querySelectorAll('div, label, span')).find(el => (el.innerText || '').trim().toLowerCase().startsWith('address'));
                                if (addrCard) addrCard.click();
                                btn.click();
                            }
                        }
                    """)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass

                # 2. Parse all known demographic details
                addr_data = self._parse_address_components(facts)

                # 3. Autofill individual form fields
                if addr_data.get("care_of"):
                    await self._smart_fill(
                        page,
                        ['input[name*="careOf" i]', 'input[name*="co" i]', 'input[placeholder*="Care of" i]', 'input[id*="careOf" i]'],
                        addr_data["care_of"],
                    )

                if addr_data.get("house"):
                    await self._smart_fill(
                        page,
                        ['input[name*="house" i]', 'input[name*="flat" i]', 'input[name*="building" i]', 'input[id*="house" i]', 'textarea[name*="house" i]'],
                        addr_data["house"],
                    )

                if addr_data.get("street"):
                    await self._smart_fill(
                        page,
                        ['input[name*="street" i]', 'input[name*="road" i]', 'input[name*="lane" i]', 'input[id*="street" i]'],
                        addr_data["street"],
                    )

                if addr_data.get("landmark"):
                    await self._smart_fill(
                        page,
                        ['input[name*="landmark" i]', 'input[id*="landmark" i]'],
                        addr_data["landmark"],
                    )

                if addr_data.get("area"):
                    await self._smart_fill(
                        page,
                        ['input[name*="area" i]', 'input[name*="locality" i]', 'input[name*="sector" i]', 'input[id*="area" i]'],
                        addr_data["area"],
                    )

                if addr_data.get("pincode"):
                    await self._smart_fill(
                        page,
                        ['input[name*="pincode" i]', 'input[name*="pin" i]', 'input[placeholder*="PIN" i]', 'input[placeholder*="Pincode" i]', 'input[id*="pin" i]'],
                        addr_data["pincode"],
                    )

                if addr_data.get("city"):
                    await self._smart_fill(
                        page,
                        ['input[name*="vtc" i]', 'input[name*="city" i]', 'input[name*="town" i]'],
                        addr_data["city"],
                    )

                if addr_data.get("new_address") and not addr_data.get("house"):
                    await self._smart_fill(
                        page,
                        ['textarea[name*="address" i]', 'textarea', 'input[type="text"]'],
                        addr_data["new_address"],
                    )

                # 4. Handle cascading VTC dropdown
                vtc_res = await self._select_dropdown_option(
                    page,
                    ['select[name*="vtc" i]', 'select[formcontrolname*="vtc" i]', 'select[id*="vtc" i]', 'mat-select[formcontrolname*="vtc" i]'],
                    addr_data.get("vtc", ""),
                    "Village/Town/City",
                )
                logger.info(f"VTC dropdown result: {vtc_res}")

                # 5. Handle cascading Post Office dropdown (prioritizing mat-select controls)
                po_res = await self._select_dropdown_option(
                    page,
                    [
                        'mat-select[formcontrolname*="postOffice" i]',
                        'mat-select[id*="postOffice" i]',
                        'mat-select[formcontrolname*="po" i]',
                        'mat-select[id*="po" i]',
                        '[role="combobox"][id*="postOffice" i]',
                        '[role="combobox"][id*="po" i]',
                        'select[name*="postOffice" i]',
                        'select[formcontrolname*="postOffice" i]',
                        'select[id*="po" i]',
                    ],
                    addr_data.get("post_office", ""),
                    "Post Office",
                )
                logger.info(f"Post Office dropdown result: {po_res}")

                # 6. Validate mandatory form fields before clicking Next/Proceed
                val_status = await self._validate_address_stage(page)
                logger.info(f"Address stage validation status: {val_status}")

                value_result = await self._verify_address_values(session, addr_data, val_status)
                if value_result is not None:
                    return value_result
                if val_status.get("pin_valid") and val_status.get("vtc_selected") and val_status.get("po_selected"):
                    self._mark_dispatch(session)
                    await self._smart_click_or_submit(
                        page,
                        target_texts=["Next", "Proceed", "Save & Continue", "Submit", "Continue"],
                        selectors=[
                            'button:has-text("Next")',
                            'button:has-text("Proceed")',
                            'button:has-text("Save & Continue")',
                            'button[type="submit"]',
                            'input[type="submit"]',
                        ],
                    )
                    logger.info("Address progression action attempted; inspecting document destination.")
                    return await self._verify_document_destination(session)
                else:
                    logger.warning(f"Address form validation incomplete: PIN valid={val_status.get('pin_valid')}, VTC selected={val_status.get('vtc_selected')}, Post Office selected={val_status.get('po_selected')}. Next click postponed.")

            elif stage == PortalStage.STAGE_4_DOCUMENT:
                # No established UIDAI upload/acceptance signal exists in this implementation.
                # Keep the authenticated browser and do not click a generic progression button.
                if (session.authentication_page is None or session.authentication_context is None
                        or session.authentication_browser is None):
                    return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                        message="Supporting-document handling requires the established authenticated browser session.")
                continuity = self._check_authentication_continuity(session)
                if continuity is not None:
                    return continuity
                authentication = await self._verify_authentication(session)
                if authentication.status == ExecutionOutcome.UNKNOWN:
                    # The document page legitimately replaces the Services dashboard.
                    # This establishes page/session evidence only, never upload acceptance.
                    destination = await self._verify_document_destination(session)
                    if destination.status == ExecutionOutcome.VERIFIED_SUCCESS:
                        authentication = destination
                if authentication.status != ExecutionOutcome.VERIFIED_SUCCESS:
                    return authentication
                continuity = self._check_authentication_continuity(session)
                if continuity is not None:
                    return continuity
                try:
                    # Reuse the existing body reader; do not invent upload selectors.
                    body = (await session.page.locator("body").inner_text(timeout=5000)).casefold()
                except Exception:
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                        message="Supporting-document status inspection timed out or failed. No upload or acceptance was verified; inspect the existing portal without repeating the action automatically.")
                if "required document missing" in body:
                    return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                        message="The page reports a required supporting document is missing.")
                if any(error in body for error in (
                        "unsupported file type", "invalid document", "upload failed",
                        "validation error", "file rejected")):
                    return ActionExecutionResult(status=ExecutionOutcome.FAILED,
                        message="The page reports a supporting-document upload or validation error.")
                return ActionExecutionResult(
                    status=ExecutionOutcome.UNKNOWN,
                    message="Supporting-document acceptance is UNKNOWN: no documented official upload response or acceptance state bound to the selected file is available. Local selection and upload-page visibility are insufficient. Capture the post-upload status without final submission; the document stage remains pending.",
                )

            elif stage == PortalStage.STAGE_5_REVIEW:
                guard = await self._validate_final_submission(session)
                if guard is not None:
                    if session.final_review.approved_binding is not None:
                        session.final_review.invalidate()
                    return guard
                # Never silently agree to declarations that were not reviewed.
                try:
                    checkboxes = await page.query_selector_all('input[type="checkbox"]')
                    for cb in checkboxes:
                        if not await cb.is_checked():
                            session.final_review.invalidate()
                            return ActionExecutionResult(status=ExecutionOutcome.NEEDS_USER,
                                message="Review and resolve unchecked portal declarations, then review and approve the submission again.")
                except Exception:
                    session.final_review.invalidate()
                    return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,
                        message="Portal declarations could not be inspected; final submission was not attempted.")

                # Recheck after awaited portal inspection, immediately before the action.
                continuity = self._check_authentication_continuity(session)
                reason = session.final_review.validate(submission_package(session))
                if continuity is not None or reason:
                    session.final_review.invalidate()
                    return continuity if continuity is not None else ActionExecutionResult(status=ExecutionOutcome.BLOCKED, message=reason)
                # One explicit approval permits one attempt; retry requires fresh review/approval.
                session.final_review.invalidate()
                await self._smart_click_or_submit(
                    page,
                    target_texts=["Submit", "Make Payment", "Pay", "Proceed to Payment", "Confirm & Submit", "Confirm"],
                    selectors=[
                        'button:has-text("Submit")',
                        'button:has-text("Make Payment")',
                        'button:has-text("Pay")',
                        'button[type="submit"]',
                    ],
                )
                logger.info("Executed Final Submit on UIDAI portal.")

        except Exception:
            return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message="Portal action raised an exception; external outcome is unverified. Inspect the existing portal; do not repeat automatically.")
        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN, message=f"{stage.value}: action outcome is unverified. No authoritative receipt or destination evidence was established; human inspection is required.")

    async def _select_dropdown_option(
        self,
        page: Any,
        selector_patterns: List[str],
        target_value: str,
        field_label: str,
    ) -> Dict[str, Any]:
        """
        Detects standard <select> or Angular mat-select controls and selects an option matching target_value.
        Strict matching rule: Requires exact normalized string match.
        Returns dict with status: 'selected', 'multiple_matches', 'no_match', 'not_found', or 'missing_value'.
        """
        if not target_value or not target_value.strip():
            return {
                "status": "missing_value",
                "message": f"No verified {field_label} provided in execution context.",
            }

        norm_target = " ".join(target_value.strip().lower().split())

        for sel in selector_patterns:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue

                tag_name = await loc.evaluate("el => el.tagName.toLowerCase()")
                role_attr = str((await loc.get_attribute("role")) or "")
                if tag_name == "select":
                    try:
                        await page.wait_for_selector(
                            f"{sel} option:not([value='']):not([value='null'])",
                            timeout=5000,
                        )
                    except Exception:
                        pass

                    options_data = await loc.evaluate("""
                        el => Array.from(el.options).map(o => ({
                            value: o.value,
                            text: (o.text || o.innerText || '').trim(),
                            disabled: o.disabled
                        }))
                    """)

                    valid_options = [
                        o for o in options_data
                        if o["value"] and o["text"] and not any(
                            ph in o["text"].lower() for ph in ["select", "choose", "--"]
                        )
                    ]

                    exact_matches = [
                        o for o in valid_options
                        if " ".join(o["text"].lower().split()) == norm_target
                    ]

                    if len(exact_matches) == 1:
                        val_to_select = exact_matches[0]["value"]
                        await loc.select_option(value=val_to_select)
                        await loc.dispatch_event("change")
                        await loc.dispatch_event("input")
                        return {"status": "selected", "value": exact_matches[0]["text"]}
                    elif len(exact_matches) > 1:
                        return {
                            "status": "multiple_matches",
                            "options": [o["text"] for o in exact_matches],
                            "message": f"Multiple exact matches found for {field_label} '{target_value}'.",
                        }
                    else:
                        return {
                            "status": "no_match",
                            "available_options": [o["text"] for o in valid_options],
                            "message": f"No exact match found for {field_label} '{target_value}'. Available: {[o['text'] for o in valid_options]}",
                        }

                elif tag_name == "mat-select" or "combobox" in role_attr:
                    await loc.click()
                    # Explicitly wait for Angular CDK overlay container options to mount in DOM (timeout 4000ms)
                    overlay_selector = ".cdk-overlay-container mat-option, .cdk-overlay-container [role='option'], mat-option, [role='option']"
                    try:
                        await page.wait_for_selector(overlay_selector, timeout=4000)
                    except Exception as wait_err:
                        logger.debug(f"CDK overlay wait note: {wait_err}")

                    mat_options = page.locator(overlay_selector)
                    count = await mat_options.count()
                    available_texts = []
                    matching_locators = []
                    for i in range(count):
                        opt = mat_options.nth(i)
                        txt = (await opt.inner_text()).strip()
                        if txt and not any(ph in txt.lower() for ph in ["select", "choose"]):
                            available_texts.append(txt)
                            if " ".join(txt.lower().split()) == norm_target:
                                matching_locators.append((opt, txt))

                    if len(matching_locators) == 1:
                        selected_opt, selected_txt = matching_locators[0]
                        await selected_opt.click()
                        await page.wait_for_timeout(300)
                        disp_txt = (await loc.inner_text()).strip()
                        return {"status": "selected", "value": selected_txt, "displayed_text": disp_txt}
                    elif len(matching_locators) > 1:
                        await page.keyboard.press("Escape")
                        return {
                            "status": "multiple_matches",
                            "options": [t for _, t in matching_locators],
                            "message": f"Multiple exact matches found for {field_label} '{target_value}'.",
                        }
                    else:
                        await page.keyboard.press("Escape")
                        return {
                            "status": "no_match",
                            "available_options": available_texts,
                            "message": f"No exact match found for {field_label} '{target_value}'. Available: {available_texts}",
                        }
            except Exception as err:
                logger.debug(f"Dropdown selection attempt on '{sel}' note: {err}")
                continue

        return {"status": "not_found", "message": f"{field_label} dropdown control not found on page."}

    async def _validate_address_stage(self, page: Any) -> Dict[str, Any]:
        """
        Validates that mandatory fields (PIN, VTC, Post Office) have non-empty valid selections before proceeding.
        """
        try:
            res = await page.evaluate("""
                () => {
                    const pinEl = document.querySelector('input[name*="pincode" i], input[name*="pin" i], input[placeholder*="PIN" i], input[placeholder*="Pincode" i], input[id*="pin" i]');
                    const pinVal = pinEl ? (pinEl.value || '').trim() : '';

                    const vtcEl = document.querySelector('select[name*="vtc" i], select[formcontrolname*="vtc" i], select[id*="vtc" i], mat-select[formcontrolname*="vtc" i]');
                    let vtcSelected = false;
                    let vtcVal = '';
                    if (vtcEl) {
                        if (vtcEl.tagName.toLowerCase() === 'select') {
                            const opt = vtcEl.options[vtcEl.selectedIndex];
                            vtcVal = opt ? (opt.text || opt.value || '').trim() : '';
                            vtcSelected = Boolean(vtcEl.value && !vtcVal.toLowerCase().includes('select'));
                        } else {
                            vtcVal = (vtcEl.innerText || '').trim();
                            vtcSelected = Boolean(vtcVal && !vtcVal.toLowerCase().includes('select'));
                        }
                    }

                    const poEl = document.querySelector('select[name*="postOffice" i], select[formcontrolname*="postOffice" i], select[id*="po" i], select[id*="postOffice" i], mat-select[formcontrolname*="postOffice" i]');
                    let poSelected = false;
                    let poVal = '';
                    if (poEl) {
                        if (poEl.tagName.toLowerCase() === 'select') {
                            const opt = poEl.options[poEl.selectedIndex];
                            poVal = opt ? (opt.text || opt.value || '').trim() : '';
                            poSelected = Boolean(poEl.value && !poVal.toLowerCase().includes('select'));
                        } else {
                            poVal = (poEl.innerText || '').trim();
                            poSelected = Boolean(poVal && !poVal.toLowerCase().includes('select'));
                        }
                    }

                    return {
                        pin_valid: /^[1-9][0-9]{5}$/.test(pinVal),
                        vtc_selected: vtcSelected,
                        po_selected: poSelected,
                        vtc_val: vtcVal,
                        po_val: poVal
                    };
                }
            """)
            return res
        except Exception as e:
            logger.debug(f"Address validation eval note: {e}")
            return {"pin_valid": False, "vtc_selected": False, "po_selected": False}

    async def _smart_fill(self, page: Any, selector_patterns: List[str], value: str) -> bool:
        if not value or not page:
            return False
        for pattern in selector_patterns:
            try:
                loc = page.locator(pattern).first
                if await loc.count() > 0:
                    await loc.scroll_into_view_if_needed()
                    await loc.click()
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await loc.press_sequentially(str(value), delay=25)

                    # Update React/Angular value tracker and dispatch events
                    await page.evaluate("""
                        ([sel, val]) => {
                            const el = document.querySelector(sel);
                            if (el) {
                                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                                if (nativeSetter) nativeSetter.call(el, val);
                                else el.value = val;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }
                    """, [pattern, str(value)])
                    return True
            except Exception:
                continue
        return False

    async def _smart_click_or_submit(
        self,
        page: Any,
        target_texts: List[str],
        selectors: Optional[List[str]] = None,
    ) -> bool:
        if not page:
            return False
        clicked = False

        # 1. Try exact Playwright selector locators
        if selectors:
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True, timeout=2000)
                        clicked = True
                        break
                except Exception:
                    continue

        # 2. Try text match locators
        if not clicked:
            for txt in target_texts:
                try:
                    loc = page.locator(f'button:has-text("{txt}"), a:has-text("{txt}"), [role="button"]:has-text("{txt}"), input[value*="{txt}" i]').first
                    if await loc.count() > 0:
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True, timeout=2000)
                        clicked = True
                        break
                except Exception:
                    continue

        # 3. JavaScript evaluate across DOM & iframes to find and dispatch click
        if not clicked:
            try:
                clicked = await page.evaluate("""
                    (texts) => {
                        const findAndClick = (doc) => {
                            const candidates = Array.from(doc.querySelectorAll('button, input[type="submit"], input[type="button"], a, [role="button"], div[tabindex]'));
                            for (const txt of texts) {
                                const lower = txt.toLowerCase();
                                for (const el of candidates) {
                                    const elText = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                                    if (elText.includes(lower) && el.offsetParent !== null && !el.disabled) {
                                        el.scrollIntoView();
                                        el.click();
                                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                                        return true;
                                    }
                                }
                            }
                            const form = doc.querySelector('form');
                            if (form && typeof form.requestSubmit === 'function') {
                                form.requestSubmit();
                                return true;
                            }
                            return false;
                        };

                        if (findAndClick(document)) return true;
                        for (const frame of Array.from(document.querySelectorAll('iframe'))) {
                            try {
                                if (frame.contentDocument && findAndClick(frame.contentDocument)) return true;
                            } catch (e) {}
                        }
                        return false;
                    }
                """, target_texts)
            except Exception as js_err:
                logger.debug(f"JS smart click error: {js_err}")

        # 4. As extra guarantee, press Enter key
        try:
            await page.keyboard.press("Enter")
        except Exception:
            pass

        return clicked

    def _fallback_open_browser(self) -> None:
        try:
            chrome_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
            ]
            browser_binary = next((p for p in chrome_paths if os.path.exists(p) and os.access(p, os.X_OK)), None)
            if browser_binary:
                subprocess.Popen(
                    [browser_binary, "--new-window", UIDAI_OFFICIAL_URL],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                webbrowser.open_new(UIDAI_OFFICIAL_URL)
        except Exception as err:
            logger.warning(f"Fallback browser open failed: {err}")


# Global interactive manager instance
interactive_manager = InteractivePortalManager()
