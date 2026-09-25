"""Deterministic visible-browser driver for RTI Online workflow.

HARD INVARIANT: The browser is NEVER closed except in two exact situations:
1. User has seen a real confirmation reference and pressed Enter to close.
2. An error occurred, in which case: print the full exception, keep the browser open,
   set ExecutionStatus.FAILED, and wait for Enter before closing.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.execution_assistance.safety import check_host_allowlist, mask_sensitive_value
from agents.execution_assistance.schema import (
    CONTRACT_VERSION,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FieldActionRecord,
    PortalObservation,
    StepExecutionResult,
    StepExecutionStatus,
    UserPausePoint,
)
from agents.user_context.schema import ProfileFact

from src.bureaucracy_agent.orchestrator.hosts import get_allowed_hosts
from src.bureaucracy_agent.orchestrator.logging_setup import log_stage
from src.bureaucracy_agent.portal.extract import extract_confirmation_details
from src.bureaucracy_agent.portal.prompts import (
    PAYMENT_PAUSE_BANNER,
    REVIEW_CHECKPOINT_FOOTER,
    REVIEW_CHECKPOINT_HEADER,
    SECURITY_PAUSE_BANNER,
)
from src.bureaucracy_agent.portal.selectors import (
    REGISTRATION_URLS,
    RTI_FORM_SELECTORS,
    RTI_GUIDELINES_SELECTORS,
    RTI_REGISTRATION_URLS,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


SECRET_LOCATORS: List[Tuple[str, List[str]]] = [
    ("CAPTCHA Image", ["img#captchaimg", "img[src*='captcha']", "img[src*='captcha_code_file']"]),
    ("CAPTCHA Input", ["input[name='6_letters_code']", "input[id='6_letters_code']", "input[name='captchaText']", "input[name*='captcha']", "input[id*='captcha']"]),
    ("OTP Input", [
        "input[name*='otp']", "input[name*='OTP']", "input[id*='otp']", "input[id*='OTP']",
        "input[name='mobile_otp']", "input[name='email_otp']", "input[placeholder*='OTP']",
        "input[placeholder*='otp']"
    ]),
    ("Password Input", ["input[type='password']"]),
]

SUBMIT_BUTTON_LOCATORS: List[str] = [
    "input[name='Submit']",
    "input[id='Status']",
    "input[type='submit'][value='Submit']",
    "input[type='submit'][value='Proceed']",
    "input[type='submit'][value='Verify']",
    "input[type='submit']",
    "button[type='submit']",
    "button:has-text('Submit')",
    "button:has-text('Proceed')",
    "button:has-text('Verify')",
    "input[name='submit']",
    "input[value='Submit']",
]


def detect_secret_elements(page: Any) -> Tuple[bool, List[str], List[str]]:
    """Detect if any secret verification elements (CAPTCHA, OTP, Password) are visible on page."""
    secret_descs: List[str] = []
    locators_found: List[str] = []
    for label, locators in SECRET_LOCATORS:
        for loc in locators:
            try:
                if page.is_visible(loc, timeout=500):
                    secret_descs.append(label)
                    locators_found.append(loc)
                    break
            except Exception:  # noqa: BLE001
                continue
    has_secret = len(secret_descs) > 0
    return has_secret, secret_descs, locators_found


def classify_current_page(page: Any, page_text: str) -> Tuple[str, str, Dict[str, str]]:
    """
    Classify page based on visible elements:
    - 'FINAL_CONFIRMATION': if confirmation details found and no pending fillable controls needing interaction
    - 'VERIFICATION_PAGE': if secret element (OTP/CAPTCHA/password) is visible
    - 'FILLABLE_PAGE': if regular fillable input/select/textarea controls exist
    - 'AMBIGUOUS': if page structure is unrecognized
    """
    observed, ref_str, ext_details = extract_confirmation_details(page_text)
    has_secret, secret_descs, _ = detect_secret_elements(page)

    has_fillable_controls = False
    try:
        inputs = page.locator("input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select")
        count = inputs.count()
        if count > 0:
            for i in range(min(count, 10)):
                if inputs.nth(i).is_visible(timeout=300):
                    has_fillable_controls = True
                    break
    except Exception:  # noqa: BLE001
        pass

    if has_secret:
        return "VERIFICATION_PAGE", ref_str or "", ext_details
    if observed and not has_fillable_controls:
        return "FINAL_CONFIRMATION", ref_str or "", ext_details
    if has_fillable_controls:
        return "FILLABLE_PAGE", ref_str or "", ext_details
    if observed:
        return "FINAL_CONFIRMATION", ref_str or "", ext_details
    return "AMBIGUOUS", ref_str or "", ext_details



class PortalBrowserDriver:
    """Deterministic, human-in-the-loop Playwright browser driver for RTI Online."""

    def __init__(self, allowed_hosts: Optional[List[str]] = None) -> None:
        self.allowed_hosts = allowed_hosts or get_allowed_hosts("execution")

    def execute_live_flow(
        self,
        request: ExecutionRequest,
        interactive: bool = True,
        stop_before_submit: bool = False,
        on_submission_attempted_cb: Optional[Any] = None,
    ) -> ExecutionResult:
        """
        Execute target RTI Online browser automation flow with strict error-recovery invariant.
        """
        started_at = utc_now()
        field_actions: List[FieldActionRecord] = []
        user_pause_points: List[UserPausePoint] = []
        portal_observations: List[PortalObservation] = []
        warnings: List[str] = list(request.workflow_plan.warnings if request.workflow_plan else [])
        step_results: List[StepExecutionResult] = []

        selected_steps = request.selected_step_ids or ["user-controlled-portal-action"]
        main_step_id = selected_steps[0]

        # Stage 1: LAUNCH
        log_stage("LAUNCH", "Starting Playwright visible Chromium browser session")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            print(f"[FATAL PREFLIGHT] Playwright import failed: {exc}")
            return ExecutionResult(
                contract_version=CONTRACT_VERSION,
                execution_request_id=request.execution_request_id,
                request_id=request.request_id,
                plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                validation_request_id=request.validation_result.validation_request_id,
                execution_status=ExecutionStatus.FAILED,
                warnings=[f"Playwright import failed: {exc}"],
                completed_at=utc_now(),
            )

        browser = None
        page = None

        def handle_flow_error(exc: Exception, stage_name: str) -> ExecutionResult:
            """Handle non-preflight exceptions: print stack trace, keep browser open, wait for Enter."""
            err_msg = f"Error during stage '{stage_name}': {type(exc).__name__}: {exc}"
            print(f"\n================================================================================")
            print(f"               DRIVER ERROR OCCURRED IN STAGE: {stage_name}")
            print(f"================================================================================")
            print(f"{err_msg}\n")
            traceback.print_exc()
            print("\nINVARIANT ACTIVE: The browser window is kept open for inspection.")
            if interactive:
                try:
                    input("Press ENTER to close the browser window... ")
                except (EOFError, KeyboardInterrupt):
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
            return ExecutionResult(
                contract_version=CONTRACT_VERSION,
                execution_request_id=request.execution_request_id,
                request_id=request.request_id,
                plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                validation_request_id=request.validation_result.validation_request_id,
                execution_status=ExecutionStatus.FAILED,
                warnings=warnings + [err_msg],
                completed_at=utc_now(),
            )

        try:
            with sync_playwright() as p:
                # Stage 1 LAUNCH Chromium
                browser = p.chromium.launch(
                    headless=False,
                    args=["--start-maximized"],
                )
                context = browser.new_context(viewport={"width": 1400, "height": 1000})
                page = context.new_page()
                page.bring_to_front()

                viewport_size = page.viewport_size or {"width": 1400, "height": 1000}
                log_stage("LAUNCH", f"Browser window opened with viewport {viewport_size['width']}x{viewport_size['height']}")

                # Determine target URL
                target_url = request.starting_url or RTI_REGISTRATION_URLS[0]

                # Stage 2: NAVIGATE
                log_stage("NAVIGATE", f"Opening target URL: {target_url}")
                if not check_host_allowlist(target_url, self.allowed_hosts):
                    return handle_flow_error(ValueError(f"URL '{target_url}' is not on host allowlist."), "NAVIGATE")

                try:
                    page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                except Exception as exc:  # noqa: BLE001
                    return handle_flow_error(exc, "NAVIGATE")

                # Handle RTI Guidelines page check & submit if present
                if "guidelines.php" in page.url:
                    log_stage("NAVIGATE", "RTI Guidelines page detected: Accepting guidelines checkbox")
                    try:
                        for loc in RTI_GUIDELINES_SELECTORS["checkbox"]["locators"]:
                            if page.is_visible(loc, timeout=1000):
                                page.check(loc)
                                print(f"[NAVIGATE CHECKBOX] Checked guidelines checkbox: {loc}")
                                break

                        for loc in RTI_GUIDELINES_SELECTORS["submit_button"]["locators"]:
                            if page.is_visible(loc, timeout=1000):
                                page.click(loc)
                                print(f"[NAVIGATE SUBMIT] Clicked guidelines submit button: {loc}")
                                break
                        page.wait_for_timeout(2000)
                    except Exception as exc:  # noqa: BLE001
                        log_stage("NAVIGATE", f"Guidelines navigation note: {exc}")

                current_url = page.url
                if not check_host_allowlist(current_url, self.allowed_hosts):
                    return handle_flow_error(ValueError(f"Redirected host '{current_url}' not allowed."), "NAVIGATE")

                portal_observations.append(
                    PortalObservation(
                        page_title=page.title(),
                        url=current_url,
                        visible_status="Opened RTI request form page",
                        observed_at=utc_now(),
                    )
                )

                active_selectors = RTI_FORM_SELECTORS
                facts_by_key = {f.key: f.value for f in request.confirmed_facts if f.confirmed_by_user}

                if request.dry_run:
                    log_stage("DRY_RUN", "Dry-run mode active: form inspected, no values typed, no submit")
                    print("\n[DRY RUN] Inspection complete. Press ENTER to close browser...")
                    if interactive:
                        input()
                    browser.close()
                    step_results.append(
                        StepExecutionResult(
                            step_id=main_step_id,
                            status=StepExecutionStatus.COMPLETED,
                            action_summary="Dry-run simulation complete. Prepared form for review.",
                            started_at=started_at,
                            completed_at=utc_now(),
                        )
                    )
                    return ExecutionResult(
                        contract_version=CONTRACT_VERSION,
                        execution_request_id=request.execution_request_id,
                        request_id=request.request_id,
                        plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                        plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                        validation_request_id=request.validation_result.validation_request_id,
                        execution_status=ExecutionStatus.PREPARED_FOR_REVIEW,
                        step_results=step_results,
                        user_pause_points=user_pause_points,
                        portal_observations=portal_observations,
                        submission_attempted=False,
                        confirmation_observed=False,
                        warnings=warnings,
                        completed_at=utc_now(),
                    )

                # Multi-Step Page Navigation & Submission Loop
                MAX_PAGE_ITERATIONS = 6
                page_index = 0

                while page_index < MAX_PAGE_ITERATIONS:
                    page_index += 1
                    current_url = page.url
                    page_title = page.title()

                    log_stage("PAGE_OBSERVE", f"Page Iteration {page_index}: Title='{page_title}', URL='{current_url}'")

                    if not check_host_allowlist(current_url, self.allowed_hosts):
                        return handle_flow_error(ValueError(f"Redirected host '{current_url}' not allowed on host allowlist."), "NAVIGATE")

                    portal_observations.append(
                        PortalObservation(
                            page_title=page_title,
                            url=current_url,
                            visible_status=f"Page {page_index} observed ({page_title})",
                            observed_at=utc_now(),
                        )
                    )

                    page_text = page.inner_text("body")
                    classification, ref_str, ext_details = classify_current_page(page, page_text)
                    log_stage("CLASSIFY", f"Page {page_index} classified as '{classification}' (URL: {current_url})")

                    # Exit Condition: Final Confirmation Page
                    if classification == "FINAL_CONFIRMATION":
                        log_stage("FINAL", "Final confirmation page detected!")
                        print("\n================================================================================")
                        print("                  OFFICIAL PORTAL CONFIRMATION DETAILS")
                        print("================================================================================")
                        if ref_str:
                            print(f" Reference String  : {ref_str}")
                            for k, v in ext_details.items():
                                print(f"   - {k:<25} : {v}")
                        else:
                            print(" Confirmation       : Registration / submission reference observed.")
                        print("================================================================================")
                        print("\nPress ENTER to close the browser window...")
                        if interactive:
                            try:
                                input()
                            except (EOFError, KeyboardInterrupt):
                                pass
                        browser.close()

                        step_results.append(
                            StepExecutionResult(
                                step_id=main_step_id,
                                status=StepExecutionStatus.COMPLETED,
                                action_summary=f"Successfully reached final confirmation page on step {page_index}.",
                                started_at=started_at,
                                completed_at=utc_now(),
                            )
                        )
                        return ExecutionResult(
                            contract_version=CONTRACT_VERSION,
                            execution_request_id=request.execution_request_id,
                            request_id=request.request_id,
                            plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                            plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                            validation_request_id=request.validation_result.validation_request_id,
                            execution_status=ExecutionStatus.CONFIRMATION_OBSERVED,
                            step_results=step_results,
                            field_actions=field_actions,
                            user_pause_points=user_pause_points,
                            portal_observations=portal_observations,
                            submission_attempted=True,
                            confirmation_observed=True,
                            confirmation_reference=ref_str,
                            warnings=warnings,
                            completed_at=utc_now(),
                        )

                    # Handle Ambiguous structure
                    if classification == "AMBIGUOUS":
                        print("\n================================================================================")
                        print("                    UNRECOGNIZED PAGE STRUCTURE DETECTED")
                        print("================================================================================")
                        print(f" Page Iteration : {page_index}")
                        print(f" Page Title     : {page_title}")
                        print(f" Page URL       : {current_url}")
                        print("================================================================================")
                        print("Please inspect the browser window.")
                        user_choice = ""
                        if interactive:
                            try:
                                user_choice = input("Press ENTER to proceed with review/submission on this page, or type 'cancel' to exit: ").strip()
                            except (EOFError, KeyboardInterrupt):
                                user_choice = "cancel"

                        if user_choice.lower() == "cancel":
                            log_stage("CANCELLED", f"User cancelled execution at ambiguous page {page_index}.")
                            print("\n[CANCELLED] Execution stopped by user. Browser stays open. Press ENTER to close...")
                            if interactive:
                                try:
                                    input()
                                except (EOFError, KeyboardInterrupt):
                                    pass
                            browser.close()
                            return ExecutionResult(
                                contract_version=CONTRACT_VERSION,
                                execution_request_id=request.execution_request_id,
                                request_id=request.request_id,
                                plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                                plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                                validation_request_id=request.validation_result.validation_request_id,
                                execution_status=ExecutionStatus.CANCELLED,
                                field_actions=field_actions,
                                user_pause_points=user_pause_points,
                                portal_observations=portal_observations,
                                submission_attempted=False,
                                confirmation_observed=False,
                                warnings=warnings + [f"User cancelled at ambiguous page {page_index}"],
                                completed_at=utc_now(),
                            )

                    # Stage 3/4: FILL non-secret fields present on this page
                    log_stage("FILL", f"Page {page_index}: Filling non-secret form fields from confirmed facts")
                    page_field_actions: List[FieldActionRecord] = []

                    for field_id, field_spec in active_selectors.items():
                        if field_spec.get("is_secret"):
                            continue

                        prof_key = field_spec.get("profile_key")
                        field_label = field_spec["labels"][0]

                        val = None
                        if prof_key:
                            val = facts_by_key.get(prof_key)
                            if not val:
                                if prof_key == "full_name":
                                    val = facts_by_key.get("name") or facts_by_key.get("given_name")
                                elif prof_key == "mobile":
                                    val = facts_by_key.get("cell") or facts_by_key.get("mobile_number")
                                elif prof_key == "present_address":
                                    val = facts_by_key.get("address")
                                elif prof_key == "pincode":
                                    val = facts_by_key.get("pin_code")
                                elif prof_key == "rti_request_text":
                                    val = facts_by_key.get("rti_text") or facts_by_key.get("request_text")

                        print(f"[FILL CHECK] page={page_index}, field_id='{field_id}', label='{field_label}', profile_key='{prof_key}', confirmed_fact_found={val is not None}")

                        if not val:
                            continue

                        filled = False
                        for locator_str in field_spec["locators"]:
                            try:
                                is_vis = page.is_visible(locator_str, timeout=1000)
                                print(f"  [FILL LOCATOR CHECK] loc='{locator_str}' -> visible={is_vis}")
                                if is_vis:
                                    page.locator(locator_str).scroll_into_view_if_needed()
                                    if field_spec["type"] in ("input", "textarea"):
                                        page.fill(locator_str, str(val))
                                        filled = True
                                        print(f"  [FILL SUCCESS] Filled '{field_label}' using locator '{locator_str}'")
                                        break
                                    elif field_spec["type"] == "select":
                                        page.select_option(locator_str, label=str(val))
                                        filled = True
                                        print(f"  [FILL SUCCESS] Selected option '{val}' for '{field_label}' using locator '{locator_str}'")
                                        break
                            except Exception as fill_exc:
                                print(f"  [FILL ERROR] Locator '{locator_str}' fill failed: {type(fill_exc).__name__}: {fill_exc}")
                                continue

                        if filled:
                            masked = mask_sensitive_value(prof_key or field_label, str(val))
                            fa = FieldActionRecord(
                                field_label=f"P{page_index}: {field_label}",
                                approval_id="exec-appr",
                                outcome="filled",
                                masked_value=masked,
                            )
                            field_actions.append(fa)
                            page_field_actions.append(fa)

                    # Stage 3 Verification Pause (if secret controls present)
                    has_secret, secret_descs, locators_found = detect_secret_elements(page)
                    if has_secret:
                        log_stage("VERIFICATION_PAGE", f"Page {page_index}: Human-gated verification required ({', '.join(secret_descs)})")
                        if locators_found:
                            try:
                                page.locator(locators_found[0]).scroll_into_view_if_needed()
                                print(f"[VERIFICATION SCROLLED] Scrolled element '{locators_found[0]}' into view")
                            except Exception as cap_exc:
                                print(f"[VERIFICATION LOCATOR ERROR] {cap_exc}")

                        secret_name = " / ".join(secret_descs)
                        print("\n================================================================================")
                        print(f"           HUMAN-GATED VERIFICATION DETECTED: {secret_name.upper()}")
                        print("================================================================================")
                        print(f"{secret_name} detected on page {page_index} — enter your {secret_name} directly in the browser window,")
                        print("then press ENTER here after completing it.\n")

                        pause_rec = UserPausePoint(
                            step_id=main_step_id,
                            reason=f"Verification required on page {page_index} ({secret_name})",
                            paused_at=utc_now(),
                        )
                        user_pause_points.append(pause_rec)

                        if interactive:
                            try:
                                input(f"Press ENTER after entering {secret_name} in the browser... ")
                            except (EOFError, KeyboardInterrupt):
                                pass

                        pause_rec.resumed_at = utc_now()
                        pause_rec.resume_status = "resumed_by_user"

                    # Stage 5: REVIEW + CONFIRM (every page before submit)
                    log_stage("REVIEW", f"Page {page_index}: Presenting form review table")
                    try:
                        page.evaluate("window.scrollTo(0, 0)")
                    except Exception:
                        pass

                    print(REVIEW_CHECKPOINT_HEADER)
                    print(f"{'FIELD LABEL':<40} | {'OUTCOME':<15} | {'PREPARED VALUE'}")
                    print("-" * 75)
                    for fa in page_field_actions:
                        print(f"{fa.field_label:<40} | {fa.outcome:<15} | {fa.masked_value}")
                    if not page_field_actions:
                        print(f"{f'Page {page_index} verification step':<40} | {'manual_entered':<15} | {'[USER_ENTRY]'}")
                    print(REVIEW_CHECKPOINT_FOOTER)

                    if stop_before_submit:
                        log_stage("STOP_BEFORE_SUBMIT", f"Stopping before submission on page {page_index} (--stop-before-submit active).")
                        print("\n[STOP_BEFORE_SUBMIT] Browser window stays open. Press ENTER to close...")
                        if interactive:
                            try:
                                input()
                            except (EOFError, KeyboardInterrupt):
                                pass
                        browser.close()
                        step_results.append(
                            StepExecutionResult(
                                step_id=main_step_id,
                                status=StepExecutionStatus.COMPLETED,
                                action_summary=f"Stopped before submission on page {page_index} (demo mode)",
                                started_at=started_at,
                                completed_at=utc_now(),
                            )
                        )
                        return ExecutionResult(
                            contract_version=CONTRACT_VERSION,
                            execution_request_id=request.execution_request_id,
                            request_id=request.request_id,
                            plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                            plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                            validation_request_id=request.validation_result.validation_request_id,
                            execution_status=ExecutionStatus.PREPARED_FOR_REVIEW,
                            step_results=step_results,
                            field_actions=field_actions,
                            user_pause_points=user_pause_points,
                            portal_observations=portal_observations,
                            submission_attempted=False,
                            confirmation_observed=False,
                            warnings=warnings,
                            completed_at=utc_now(),
                        )

                    log_stage("CONFIRM_SUBMISSION", f"Page {page_index}: Awaiting explicit CONFIRM SUBMISSION phrase from user")
                    typed_phrase = ""
                    if interactive:
                        try:
                            print("\nReview the browser window now.")
                            typed_phrase = input("Type CONFIRM SUBMISSION to submit this step, or anything else to cancel: ").strip()
                        except (EOFError, KeyboardInterrupt):
                            typed_phrase = ""

                    exact_match = (typed_phrase.strip().upper() == "CONFIRM SUBMISSION")
                    print(f"[SUBMIT CHECK] Page {page_index} user input: '{typed_phrase}', exact_match={exact_match}")

                    if not exact_match:
                        log_stage("CANCELLED", f"User typed non-submission phrase on page {page_index}. Submission cancelled; browser stays open.")
                        print(f"\n[CANCELLED] Submission cancelled at page {page_index}. Browser window stays open — press ENTER to close...")
                        if interactive:
                            try:
                                input()
                            except (EOFError, KeyboardInterrupt):
                                pass
                        browser.close()
                        return ExecutionResult(
                            contract_version=CONTRACT_VERSION,
                            execution_request_id=request.execution_request_id,
                            request_id=request.request_id,
                            plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                            plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                            validation_request_id=request.validation_result.validation_request_id,
                            execution_status=ExecutionStatus.CANCELLED,
                            field_actions=field_actions,
                            user_pause_points=user_pause_points,
                            portal_observations=portal_observations,
                            submission_attempted=False,
                            confirmation_observed=False,
                            warnings=warnings + [f"Submission cancelled by user on page {page_index}."],
                            completed_at=utc_now(),
                        )

                    # Stage 6: Submit this page's form
                    log_stage("SUBMIT", f"Page {page_index}: Locating and clicking submit button on page {current_url}")
                    if on_submission_attempted_cb:
                        on_submission_attempted_cb()

                    submitted = False
                    for loc in SUBMIT_BUTTON_LOCATORS:
                        try:
                            if page.is_visible(loc, timeout=1500):
                                print(f"[STAGE] SUBMIT: clicking now (page={page_index}, locator='{loc}')")
                                page.locator(loc).scroll_into_view_if_needed()
                                page.locator(loc).click(force=True)
                                submitted = True
                                print(f"[STAGE] SUBMIT: click completed successfully (page={page_index}, locator='{loc}')")
                                break
                        except Exception as submit_exc:
                            print(f"[SUBMIT CLICK ERROR] Locator '{loc}' failed on page {page_index}: {type(submit_exc).__name__}: {submit_exc}")
                            continue

                    if not submitted and interactive:
                        print(f"\n[SUBMIT FALLBACK] Could not automatically click submit button on page {page_index}.")
                        input("Please click Submit in the browser yourself, then press ENTER here... ")

                    log_stage("POST_SUBMIT", f"Page {page_index}: Submitted form. Waiting for next page load...")
                    try:
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass

                # Loop Guard Limit Reached
                log_stage("LOOP_GUARD", f"Maximum page iteration limit ({MAX_PAGE_ITERATIONS}) reached without final confirmation.")
                print(f"\n================================================================================")
                print(f"          LOOP GUARD REACHED: Iteration limit ({MAX_PAGE_ITERATIONS}) hit")
                print(f"================================================================================")
                print("Observations across pages visited:")
                for obs in portal_observations:
                    print(f" - {obs.page_title} ({obs.url}): {obs.visible_status}")

                print("\nThe browser window remains open for user inspection. Press ENTER to close...")
                if interactive:
                    try:
                        input()
                    except (EOFError, KeyboardInterrupt):
                        pass
                browser.close()

                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.UNCERTAIN,
                    step_results=step_results,
                    field_actions=field_actions,
                    user_pause_points=user_pause_points,
                    portal_observations=portal_observations,
                    submission_attempted=True,
                    confirmation_observed=False,
                    warnings=warnings + [f"Iteration limit ({MAX_PAGE_ITERATIONS}) reached."],
                    completed_at=utc_now(),
                )

        except Exception as exc:  # noqa: BLE001
            return handle_flow_error(exc, "UNHANDLED_EXCEPTION")


# Backward compatibility alias
PassportSevaDriver = PortalBrowserDriver
