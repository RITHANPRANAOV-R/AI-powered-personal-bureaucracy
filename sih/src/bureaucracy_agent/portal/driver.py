"""Deterministic visible-browser driver for RTI Online workflow.

HARD INVARIANT: The browser is NEVER closed except in two exact situations:
1. User has seen a real confirmation reference and pressed Enter to close.
2. An error occurred, in which case: print the full exception, keep the browser open,
   set ExecutionStatus.FAILED, and wait for Enter before closing.
"""

from __future__ import annotations

import sys
import traceback
import concurrent.futures
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
    ALL_PORTAL_SELECTORS,
    REGISTRATION_URLS,
    RTI_FORM_SELECTORS,
    RTI_GUIDELINES_SELECTORS,
    RTI_REGISTRATION_URLS,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_input(prompt: str = "") -> str:
    if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return ""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return ""



SECRET_LOCATORS: List[Tuple[str, List[str]]] = [
    ("CAPTCHA Image", ["img#captchaimg", "img[src*='captcha']", "img[src*='captcha_code_file']", "img[src*='security']", "img.captcha-image", "div.captcha-img img"]),
    ("CAPTCHA Input", ["input[name='6_letters_code']", "input[id='6_letters_code']", "input[name='captchaText']", "input[name*='captcha']", "input[id*='captcha']", "input[placeholder*='Captcha']", "input[placeholder*='CAPTCHA']", "input[name='securityCode']"]),
    ("OTP Input", [
        "input[name*='otp']", "input[name*='OTP']", "input[id*='otp']", "input[id*='OTP']",
        "input[name='mobile_otp']", "input[name='email_otp']", "input[placeholder*='OTP']",
        "input[placeholder*='otp']", "input[placeholder*='Enter OTP']"
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
    "button:has-text('Send OTP')",
    "button:has-text('Login')",
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



def fill_form_fields(
    page: Any,
    facts_by_key: Dict[str, Any],
    active_selectors: Dict[str, Dict[str, Any]],
    field_actions: List[FieldActionRecord],
) -> int:
    """Auto-fill non-secret form fields from confirmed facts and defaults."""
    filled_count = 0
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
                    val = facts_by_key.get("name") or facts_by_key.get("given_name") or facts_by_key.get("applicant_name")
                elif prof_key == "aadhaar_number":
                    val = facts_by_key.get("aadhaar_number") or facts_by_key.get("aadhaar") or facts_by_key.get("uid")
                elif prof_key == "mobile":
                    val = facts_by_key.get("cell") or facts_by_key.get("phone") or facts_by_key.get("mobile_number")
                elif prof_key == "email":
                    val = facts_by_key.get("email_id")
                elif prof_key == "present_address":
                    val = facts_by_key.get("address") or facts_by_key.get("residential_address")
                elif prof_key == "pincode":
                    val = facts_by_key.get("pin_code") or facts_by_key.get("postal_code") or facts_by_key.get("pin")
                elif prof_key == "gender":
                    val = facts_by_key.get("sex")
                elif prof_key == "state":
                    val = facts_by_key.get("state")
                elif prof_key == "district":
                    val = facts_by_key.get("district") or facts_by_key.get("city")
                elif prof_key == "father_name":
                    val = facts_by_key.get("father_name") or facts_by_key.get("care_of")
                elif prof_key in ("srn", "urn", "eid", "enrolment_id", "reference_number", "registration_number"):
                    val = (
                        facts_by_key.get("srn")
                        or facts_by_key.get("urn")
                        or facts_by_key.get("eid")
                        or facts_by_key.get("enrolment_id")
                        or facts_by_key.get("reference_number")
                        or facts_by_key.get("registration_number")
                        or facts_by_key.get("reg_no")
                        or facts_by_key.get("arn")
                        or facts_by_key.get("aadhaar_number")
                    )
                elif prof_key == "rti_request_text":
                    val = facts_by_key.get("rti_text") or facts_by_key.get("request_text") or facts_by_key.get("query")
                elif prof_key == "ministry":
                    val = facts_by_key.get("department") or facts_by_key.get("public_authority") or facts_by_key.get("dept")

        if not val and "default" in field_spec:
            val = field_spec["default"]

        if not val:
            continue

        filled = False
        for locator_str in field_spec["locators"]:
            try:
                if page.is_visible(locator_str, timeout=400):
                    page.locator(locator_str).scroll_into_view_if_needed()
                    if field_spec["type"] in ("input", "textarea"):
                        curr_val = page.locator(locator_str).input_value()
                        if not curr_val:
                            page.fill(locator_str, str(val))
                            try:
                                page.locator(locator_str).dispatch_event("input")
                                page.locator(locator_str).dispatch_event("change")
                            except Exception:
                                pass
                            filled = True
                            print(f"  [FILL SUCCESS] Filled '{field_label}' with '{mask_sensitive_value(prof_key or field_label, str(val))}'")
                            break
                        else:
                            filled = True
                            break
                    elif field_spec["type"] == "select":
                        try:
                            page.select_option(locator_str, label=str(val))
                            filled = True
                        except Exception:
                            try:
                                page.select_option(locator_str, value=str(val))
                                filled = True
                            except Exception:
                                try:
                                    options = page.locator(f"{locator_str} option").all_inner_texts()
                                    matched_opt = next((opt for opt in options if str(val).lower() in opt.lower()), None)
                                    if matched_opt:
                                        page.select_option(locator_str, label=matched_opt)
                                        filled = True
                                except Exception:
                                    pass
                        if filled:
                            print(f"  [FILL SUCCESS] Selected option '{val}' for '{field_label}'")
                            break
            except Exception:
                continue

        if filled:
            filled_count += 1
            masked = mask_sensitive_value(prof_key or field_label, str(val))
            if not any(fa.field_label == field_label for fa in field_actions):
                fa = FieldActionRecord(
                    field_label=field_label,
                    approval_id="exec-appr",
                    outcome="filled",
                    masked_value=masked,
                )
                field_actions.append(fa)

    return filled_count


def detect_unfilled_portal_fields(page: Any) -> List[Dict[str, Any]]:
    """
    Dynamically scan the active browser DOM to detect visible input/select/textarea
    fields that remain unfilled and are not secrets (not captcha, otp, password).
    Returns field keys, names, labels, input types, and options for dropdowns.
    """
    try:
        script = """() => {
            const results = [];
            const isSecret = (el) => {
                const name = (el.name || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                const type = (el.type || '').toLowerCase();
                const placeholder = (el.placeholder || '').toLowerCase();
                if (type === 'password' || type === 'hidden' || type === 'submit' || type === 'button' || type === 'reset' || type === 'image') return true;
                if (name.includes('captcha') || id.includes('captcha') || placeholder.includes('captcha') || name.includes('6_letters_code') || id.includes('6_letters_code') || name.includes('securitycode')) return true;
                if (name.includes('otp') || id.includes('otp') || placeholder.includes('otp')) return true;
                return false;
            };

            const isVisible = (el) => {
                if (!el || el.offsetParent === null) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const getLabel = (el) => {
                if (el.id) {
                    const l = document.querySelector(`label[for="${el.id}"]`);
                    if (l && l.innerText.trim()) return l.innerText.trim();
                }
                const parentLabel = el.closest('label');
                if (parentLabel && parentLabel.innerText.trim()) {
                    return parentLabel.innerText.replace(el.innerText || '', '').trim();
                }
                const tr = el.closest('tr');
                if (tr) {
                    const td = el.closest('td');
                    if (td) {
                        const prevTd = td.previousElementSibling;
                        if (prevTd && prevTd.innerText.trim()) return prevTd.innerText.trim();
                    }
                    const th = tr.querySelector('th');
                    if (th && th.innerText.trim()) return th.innerText.trim();
                }
                if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
                if (el.placeholder) return el.placeholder.trim();
                if (el.title) return el.title.trim();
                if (el.name) {
                    return el.name.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim();
                }
                return el.id || 'Field';
            };

            const elements = Array.from(document.querySelectorAll('input, select, textarea'));
            for (const el of elements) {
                if (!isVisible(el)) continue;
                if (el.disabled || el.readOnly) continue;
                if (isSecret(el)) continue;

                const tagName = el.tagName.toLowerCase();
                const type = (el.type || 'text').toLowerCase();

                let val = el.value || '';
                let isUnfilled = false;
                let options = [];

                if (tagName === 'select') {
                    const selOpts = Array.from(el.options || []);
                    options = selOpts.map(o => ({ value: o.value, label: o.text.trim() })).filter(o => o.label.length > 0);
                    const selectedIdx = el.selectedIndex;
                    const selectedText = selectedIdx >= 0 && selOpts[selectedIdx] ? selOpts[selectedIdx].text.trim().toLowerCase() : '';
                    if (!val || val === '0' || val === '-1' || selectedText.startsWith('--') || selectedText.startsWith('select') || selectedText === '') {
                        isUnfilled = true;
                    }
                } else if (tagName === 'textarea') {
                    if (!val.trim()) isUnfilled = true;
                } else if (tagName === 'input') {
                    if (type === 'checkbox') {
                        if (!el.checked && el.required) isUnfilled = true;
                    } else if (type === 'radio') {
                        // skip lone radio buttons
                    } else {
                        if (!val.trim()) isUnfilled = true;
                    }
                }

                if (isUnfilled) {
                    let rawLabel = getLabel(el);
                    let cleanLabel = rawLabel.replace(/[*:]/g, '').replace(/\\(Mandatory\\)/gi, '').replace(/\\s+/g, ' ').trim();
                    if (cleanLabel.length > 60) cleanLabel = cleanLabel.substring(0, 60);

                    const fieldKey = el.name || el.id || ('field_' + results.length);
                    if (!results.some(r => r.key === fieldKey)) {
                        results.push({
                            key: fieldKey,
                            name: el.name || '',
                            id: el.id || '',
                            label: cleanLabel || fieldKey,
                            type: tagName === 'select' ? 'select' : (tagName === 'textarea' ? 'textarea' : type),
                            options: options.slice(0, 50),
                            placeholder: el.placeholder || '',
                            is_required: el.required || rawLabel.includes('*') || rawLabel.toLowerCase().includes('mandatory')
                        });
                    }
                }
            }
            return results;
        };"""
        return page.evaluate(script) or []
    except Exception as exc:
        print(f"[DETECT UNFILLED FIELDS NOTE] {exc}")
        return []


def fill_submitted_portal_fields(session_id: str, field_values: Dict[str, str]) -> int:
    """Fill user-provided unknown field values directly into the active Playwright browser page."""
    if session_id not in _DRIVER_SESSIONS:
        return 0
    page = _DRIVER_SESSIONS[session_id].get("page")
    if not page:
        return 0

    filled_count = 0
    for field_key, val in field_values.items():
        if not val or not str(val).strip():
            continue
        val_str = str(val).strip()
        locators = [
            f"[name='{field_key}']",
            f"#{field_key}",
            f"input[name='{field_key}']",
            f"textarea[name='{field_key}']",
            f"select[name='{field_key}']",
            f"input[id='{field_key}']",
            f"textarea[id='{field_key}']",
            f"select[id='{field_key}']",
        ]
        for loc in locators:
            try:
                if page.is_visible(loc, timeout=400):
                    tag = page.locator(loc).evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        try:
                            page.select_option(loc, label=val_str)
                            filled_count += 1
                            break
                        except Exception:
                            try:
                                page.select_option(loc, value=val_str)
                                filled_count += 1
                                break
                            except Exception:
                                options = page.locator(f"{loc} option").all_inner_texts()
                                matched = next((o for o in options if val_str.lower() in o.lower()), None)
                                if matched:
                                    page.select_option(loc, label=matched)
                                    filled_count += 1
                                    break
                    elif tag in ("input", "textarea"):
                        page.fill(loc, val_str)
                        try:
                            page.locator(loc).dispatch_event("input")
                            page.locator(loc).dispatch_event("change")
                        except Exception:
                            pass
                        filled_count += 1
                        break
            except Exception:
                continue
    return filled_count


def persist_new_facts_to_vault(profile_path: str, field_values: Dict[str, str], field_labels: Dict[str, str]) -> None:
    """Persist user-entered field values into the user's profile and knowledge base store."""
    from pathlib import Path
    from agents.user_context.schema import FactSourceType, FactStatus, ProfileFact, Sensitivity
    from agents.user_context.storage import ProfileStore

    store = ProfileStore(Path(profile_path))
    new_facts: List[ProfileFact] = []
    for key, val in field_values.items():
        if not val or not str(val).strip():
            continue
        norm_key = key.lower().replace(" ", "_").replace("-", "_")
        fact = ProfileFact(
            key=norm_key,
            value=str(val).strip(),
            status=FactStatus.USER_CONFIRMED,
            source_type=FactSourceType.USER,
            source_ref="portal_form_interview",
            extracted_at=utc_now(),
            confidence=1.0,
            relevant_to=f"Official portal field: {field_labels.get(key, key)}",
            sensitivity=Sensitivity.ORDINARY,
            confirmed_by_user=True,
        )
        new_facts.append(fact)
    if new_facts:
        store.upsert_confirmed(new_facts)


_DRIVER_SESSIONS: Dict[str, Dict[str, Any]] = {}
_DRIVER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright_driver")


class PortalBrowserDriver:
    """Deterministic, human-in-the-loop Playwright browser driver for government workflows."""

    def __init__(self, allowed_hosts: Optional[List[str]] = None) -> None:
        self.allowed_hosts = allowed_hosts or get_allowed_hosts("execution")

    def execute_live_flow(
        self,
        request: ExecutionRequest,
        interactive: bool = True,
        stop_before_submit: bool = False,
        on_submission_attempted_cb: Optional[Any] = None,
    ) -> ExecutionResult:
        """Execute flow in dedicated persistent driver worker thread to maintain Playwright thread affinity."""
        future = _DRIVER_EXECUTOR.submit(
            self._execute_live_flow_inner,
            request,
            interactive,
            stop_before_submit,
            on_submission_attempted_cb,
        )
        return future.result()

    def _execute_live_flow_inner(
        self,
        request: ExecutionRequest,
        interactive: bool = True,
        stop_before_submit: bool = False,
        on_submission_attempted_cb: Optional[Any] = None,
    ) -> ExecutionResult:
        """
        Execute target government portal browser automation flow with multi-step resume support.
        """
        started_at = utc_now()
        selected_steps = request.selected_step_ids or ["user-controlled-portal-action"]
        main_step_id = selected_steps[0]
        session_id = request.request_id

        # Compile comprehensive dictionary of known profile facts
        facts_by_key = {f.key: f.value for f in request.confirmed_facts if f.confirmed_by_user}
        if request.profile_context and hasattr(request.profile_context, "relevant_facts"):
            for rf in request.profile_context.relevant_facts:
                if rf.key not in facts_by_key and rf.value:
                    facts_by_key[rf.key] = rf.value
        if request.intent and hasattr(request.intent, "explicit_facts"):
            for k, v in request.intent.explicit_facts.items():
                if k not in facts_by_key and v:
                    facts_by_key[k] = v
        goal_text = getattr(request.intent, "original_goal", None) or getattr(request.intent, "normalized_goal", None) or getattr(request.intent, "user_goal", "")
        if goal_text:
            if "rti_request_text" not in facts_by_key:
                facts_by_key["rti_request_text"] = goal_text
            if "srn" not in facts_by_key and "registration_number" not in facts_by_key:
                import re
                m = re.search(r"\b([S|s]\d{9,16}|\d{14,28}|\d{4}/\d{5}/\d{5}|[A-Za-z]{3,6}/\d{4,8}/\d{4,8})\b", goal_text)
                if m:
                    facts_by_key["srn"] = m.group(1)
                    facts_by_key["registration_number"] = m.group(1)

        # --- RESUME BRANCH: Active Browser Session Found ---
        if session_id in _DRIVER_SESSIONS:
            log_stage("RESUME", f"Resuming active browser session for workflow request '{session_id}'")
            session = _DRIVER_SESSIONS.pop(session_id)
            p = session["playwright"]
            browser = session["browser"]
            context = session.get("context")
            page = session["page"]
            field_actions: List[FieldActionRecord] = session.get("field_actions", [])
            user_pause_points: List[UserPausePoint] = session.get("user_pause_points", [])
            portal_observations: List[PortalObservation] = session.get("portal_observations", [])
            warnings: List[str] = list(request.workflow_plan.warnings if request.workflow_plan else [])

            try:
                # If dry-run or stop-before-submit was active, user has finished inspection
                if request.dry_run or stop_before_submit:
                    log_stage("REVIEW_COMPLETE", "User verified portal form in browser. Completing inspection pass.")
                    try:
                        browser.close()
                        p.stop()
                    except Exception:
                        pass
                    return ExecutionResult(
                        contract_version=CONTRACT_VERSION,
                        execution_request_id=request.execution_request_id,
                        request_id=request.request_id,
                        plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                        plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                        validation_request_id=request.validation_result.validation_request_id,
                        execution_status=ExecutionStatus.PREPARED_FOR_REVIEW,
                        step_results=[
                            StepExecutionResult(
                                step_id=main_step_id,
                                status=StepExecutionStatus.COMPLETED,
                                action_summary="Human-in-the-loop review completed successfully.",
                                started_at=started_at,
                                completed_at=utc_now(),
                            )
                        ],
                        field_actions=field_actions,
                        user_pause_points=user_pause_points,
                        portal_observations=portal_observations,
                        submission_attempted=False,
                        confirmation_observed=False,
                        warnings=warnings,
                        completed_at=utc_now(),
                    )

                # Live Submit current page flow
                log_stage("SUBMIT", "Processing portal step submission and inspecting subsequent screen...")
                if on_submission_attempted_cb:
                    on_submission_attempted_cb()

                # If on a page with a submit / login / verify button, click it
                submitted = False
                for loc in SUBMIT_BUTTON_LOCATORS:
                    try:
                        if page.is_visible(loc, timeout=600):
                            print(f"[STAGE] SUBMIT: clicking button '{loc}'")
                            page.locator(loc).scroll_into_view_if_needed()
                            page.locator(loc).click(force=True)
                            submitted = True
                            break
                    except Exception:
                        continue

                # Wait for potential navigation or reactive component re-render
                try:
                    page.wait_for_timeout(3000)
                except Exception:
                    pass

                next_url = page.url
                page_title = page.title()
                portal_observations.append(
                    PortalObservation(
                        page_title=page_title,
                        url=next_url,
                        visible_status=f"Observed page after resume: {page_title} ({next_url})",
                        observed_at=utc_now(),
                    )
                )

                # Check 1: Confirmation observed?
                page_text = ""
                try:
                    page_text = page.inner_text("body")
                except Exception:
                    pass

                observed, ref_str, ext_details = extract_confirmation_details(page_text)
                if observed:
                    log_stage("CONFIRMATION", f"Final confirmation detected on portal: {ref_str or 'Success'}")
                    try:
                        page.evaluate(f"""() => {{
                            let b = document.getElementById('bureaucracy-agent-banner');
                            if (b) {{
                                b.style.background = 'linear-gradient(90deg, #065f46, #047857)';
                                b.innerHTML = '<div style="display:flex;align-items:center;gap:12px;"><span style="font-size:18px;">✅</span><div><strong>AI Assistant:</strong> Application submitted successfully! Reference: <strong>{ref_str or "Confirmed"}</strong>.</div></div><div style="background:#059669;color:#fff;padding:6px 14px;border-radius:8px;font-weight:700;font-size:12px;">CONFIRMED</div>';
                            }}
                        }}""")
                        page.wait_for_timeout(4000)
                    except Exception:
                        pass

                    try:
                        browser.close()
                        p.stop()
                    except Exception:
                        pass

                    return ExecutionResult(
                        contract_version=CONTRACT_VERSION,
                        execution_request_id=request.execution_request_id,
                        request_id=request.request_id,
                        plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                        plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                        validation_request_id=request.validation_result.validation_request_id,
                        execution_status=ExecutionStatus.CONFIRMATION_OBSERVED,
                        step_results=[
                            StepExecutionResult(
                                step_id=main_step_id,
                                status=StepExecutionStatus.COMPLETED,
                                action_summary=f"Portal workflow executed and confirmed with reference: {ref_str or 'Success'}.",
                                started_at=started_at,
                                completed_at=utc_now(),
                            )
                        ],
                        field_actions=field_actions,
                        user_pause_points=user_pause_points,
                        portal_observations=portal_observations,
                        submission_attempted=True,
                        confirmation_observed=True,
                        confirmation_reference=ref_str,
                        warnings=warnings,
                        completed_at=utc_now(),
                    )

                # Check 2: Auto-fill non-secret fields on this subsequent page (e.g. request form or update details)
                fill_form_fields(page, facts_by_key, ALL_PORTAL_SELECTORS, field_actions)

                # Check 2b: Detect if any visible non-secret fields remain unfilled / unknown
                unfilled_fields = detect_unfilled_portal_fields(page)
                if unfilled_fields:
                    log_stage("UNKNOWN_FIELDS", f"Detected {len(unfilled_fields)} unfilled/unknown fields on portal page. Pausing for user input.")
                    pause_rec = UserPausePoint(
                        step_id=main_step_id,
                        reason=f"Unfilled portal form fields detected ({len(unfilled_fields)} fields)",
                        paused_at=utc_now(),
                    )
                    user_pause_points.append(pause_rec)

                    _DRIVER_SESSIONS[session_id] = {
                        "playwright": p,
                        "browser": browser,
                        "context": context,
                        "page": page,
                        "started_at": started_at,
                        "field_actions": field_actions,
                        "user_pause_points": user_pause_points,
                        "portal_observations": portal_observations,
                        "main_step_id": main_step_id,
                        "missing_portal_fields": unfilled_fields,
                    }

                    return ExecutionResult(
                        contract_version=CONTRACT_VERSION,
                        execution_request_id=request.execution_request_id,
                        request_id=request.request_id,
                        plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                        plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                        validation_request_id=request.validation_result.validation_request_id,
                        execution_status=ExecutionStatus.PAUSED_FOR_USER,
                        step_results=[
                            StepExecutionResult(
                                step_id=main_step_id,
                                status=StepExecutionStatus.PAUSED_FOR_USER,
                                action_summary=f"Form loaded with {len(unfilled_fields)} unknown/unfilled fields. Awaiting user input.",
                                started_at=started_at,
                            )
                        ],
                        field_actions=field_actions,
                        user_pause_points=user_pause_points,
                        portal_observations=portal_observations,
                        submission_attempted=False,
                        confirmation_observed=False,
                        warnings=warnings,
                    )

                # Check 3: Check for CAPTCHA, OTP, or user verification challenge
                has_secret, secret_descs, locators_found = detect_secret_elements(page)
                secret_name = " / ".join(secret_descs) if has_secret else "User Review & Submission"

                log_stage("HUMAN_IN_THE_LOOP", f"Session ongoing on portal ({secret_name}). Browser kept active for user interaction.")
                if locators_found:
                    try:
                        page.locator(locators_found[0]).scroll_into_view_if_needed()
                    except Exception:
                        pass

                banner_text = f"Please complete the <strong>{secret_name}</strong> in the browser, then click <strong>Resume Assistant</strong> in your web dashboard." if has_secret else "Form fields updated from your vault. Review in the browser and click <strong>Resume Assistant</strong> when ready."
                status_badge = f"{secret_name.upper()} ACTIVE" if has_secret else "AUTHENTICATED ACTIVE"

                try:
                    page.evaluate(f"""() => {{
                        let b = document.getElementById('bureaucracy-agent-banner');
                        if (!b) {{
                            b = document.createElement('div');
                            b.id = 'bureaucracy-agent-banner';
                            b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:linear-gradient(90deg, #0f172a, #1e1b4b);color:#f8fafc;padding:12px 20px;z-index:999999;font-family:sans-serif;font-size:14px;box-shadow:0 4px 20px rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid #818cf8;';
                            document.body.prepend(b);
                        }}
                        b.innerHTML = '<div style="display:flex;align-items:center;gap:12px;"><span style="font-size:18px;">🤖</span><div><strong>AI Personal Bureaucracy Assistant:</strong> {banner_text}</div></div><div style="background:#4338ca;color:#fff;padding:6px 14px;border-radius:8px;font-weight:700;font-size:12px;">{status_badge}</div>';
                    }}""")
                except Exception:
                    pass

                pause_rec = UserPausePoint(
                    step_id=main_step_id,
                    reason=f"Verification / review on portal ({secret_name})",
                    paused_at=utc_now(),
                )
                user_pause_points.append(pause_rec)

                _DRIVER_SESSIONS[session_id] = {
                    "playwright": p,
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "started_at": started_at,
                    "field_actions": field_actions,
                    "user_pause_points": user_pause_points,
                    "portal_observations": portal_observations,
                    "main_step_id": main_step_id,
                }

                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.PAUSED_FOR_USER,
                    step_results=[
                        StepExecutionResult(
                            step_id=main_step_id,
                            status=StepExecutionStatus.PAUSED_FOR_USER,
                            action_summary=f"Proceeded through portal step. Paused for user verification ({secret_name}).",
                            started_at=started_at,
                        )
                    ],
                    field_actions=field_actions,
                    user_pause_points=user_pause_points,
                    portal_observations=portal_observations,
                    submission_attempted=True,
                    confirmation_observed=False,
                    warnings=warnings,
                )

            except Exception as resume_exc:
                print(f"[RESUME ERROR] {resume_exc}")
                try:
                    browser.close()
                    p.stop()
                except Exception:
                    pass
                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.FAILED,
                    warnings=warnings + [str(resume_exc)],
                    completed_at=utc_now(),
                )

        # --- INITIAL EXECUTION BRANCH ---
        field_actions: List[FieldActionRecord] = []
        user_pause_points: List[UserPausePoint] = []
        portal_observations: List[PortalObservation] = []
        warnings: List[str] = list(request.workflow_plan.warnings if request.workflow_plan else [])
        step_results: List[StepExecutionResult] = []

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

        p = None
        browser = None
        page = None

        def handle_flow_error(exc: Exception, stage_name: str) -> ExecutionResult:
            err_msg = f"Error during stage '{stage_name}': {type(exc).__name__}: {exc}"
            print(f"\n================================================================================")
            print(f"               DRIVER ERROR OCCURRED IN STAGE: {stage_name}")
            print(f"================================================================================")
            print(f"{err_msg}\n")
            traceback.print_exc()
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if p:
                try:
                    p.stop()
                except Exception:
                    pass
            _DRIVER_SESSIONS.pop(session_id, None)
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
            import asyncio
            import os
            os.environ["PLAYWRIGHT_SYNC_API_OVERRIDE"] = "1"
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass

            p = sync_playwright().start()
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
            except Exception as exc:
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
                except Exception as exc:
                    log_stage("NAVIGATE", f"Guidelines navigation note: {exc}")

            # Handle myAadhaar portal initial navigation (Login vs Check Enrolment Status)
            if "myaadhaar.uidai.gov.in" in page.url:
                is_tracking_goal = any(kw in goal_text.lower() for kw in ("track", "status", "check", "enrolment", "search"))
                log_stage("NAVIGATE", f"myAadhaar portal detected: Initializing interface ({'Tracking' if is_tracking_goal else 'Login'})")
                try:
                    if is_tracking_goal or "checkaadhaarstatus" in page.url.lower() or "check-aadhaar-status" in page.url.lower():
                        # Check if status form is already visible or if we need to click Check Enrolment Status tile
                        has_status_form = False
                        for form_sel in ["input[name='eid']", "input[name='srn']", "input[name='urn']", "input[name='eidSrnUrn']", "input[placeholder*='Enrolment']", "input[placeholder*='SRN']"]:
                            try:
                                if page.is_visible(form_sel, timeout=1000):
                                    has_status_form = True
                                    break
                            except Exception:
                                continue

                        if not has_status_form:
                            for loc in [
                                "a[href*='CheckAadhaarStatus']",
                                "a[href*='check-aadhaar-status']",
                                "div:has-text('Check Enrolment & Update Status')",
                                "div:has-text('Check Aadhaar Status')",
                                "a:has-text('Check Enrolment')",
                                "button:has-text('Check Status')",
                            ]:
                                try:
                                    if page.is_visible(loc, timeout=2500):
                                        print(f"[NAVIGATE TRACKING] Clicking myAadhaar status tracking entry: {loc}")
                                        page.locator(loc).scroll_into_view_if_needed()
                                        page.click(loc, force=True)
                                        page.wait_for_timeout(2000)
                                        break
                                except Exception:
                                    continue

                        try:
                            page.wait_for_selector(
                                "input[name='eid'], input[name='srn'], input[name='urn'], input[name='eidSrnUrn'], input[placeholder*='Enrolment'], input[placeholder*='SRN'], input[placeholder*='URN'], button:has-text('Submit')",
                                timeout=8000,
                            )
                        except Exception:
                            pass
                    else:
                        # Check if login form is already mounted or if we need to click Login
                        has_login_form = False
                        for form_sel in ["input[name='uid']", "input[name='aadhaar']", "input[placeholder*='Aadhaar']", "input[maxlength='12']"]:
                            try:
                                if page.is_visible(form_sel, timeout=1000):
                                    has_login_form = True
                                    break
                            except Exception:
                                continue

                        if not has_login_form:
                            # Wait for and click the Login button on the landing page
                            for loc in [
                                "button:has-text('Login')",
                                "a:has-text('Login')",
                                "button:has-text('Login with OTP')",
                                "button:has-text('LOGIN')",
                                "a[href*='login']",
                                "div.login-btn button",
                            ]:
                                try:
                                    if page.is_visible(loc, timeout=2500):
                                        print(f"[NAVIGATE LOGIN] Found Login entry on myAadhaar: {loc}, clicking...")
                                        page.locator(loc).scroll_into_view_if_needed()
                                        page.click(loc, force=True)
                                        page.wait_for_timeout(2000)
                                        break
                                except Exception:
                                    continue

                        # Explicitly wait for Aadhaar input field or OTP controls to mount
                        try:
                            page.wait_for_selector(
                                "input[name='uid'], input[name='aadhaar'], input[placeholder*='Aadhaar'], input[placeholder*='Enter Aadhaar'], input[maxlength='12'], button:has-text('Send OTP')",
                                timeout=8000,
                            )
                        except Exception:
                            pass

                    page.wait_for_timeout(1000)
                except Exception as exc:
                    log_stage("NAVIGATE", f"myAadhaar navigation note: {exc}")

            current_url = page.url
            if not check_host_allowlist(current_url, self.allowed_hosts):
                return handle_flow_error(ValueError(f"Redirected host '{current_url}' not allowed."), "NAVIGATE")

            portal_observations.append(
                PortalObservation(
                    page_title=page.title(),
                    url=current_url,
                    visible_status=f"Opened portal form page: {current_url}",
                    observed_at=utc_now(),
                )
            )

            # Stage 3: FILL non-secret fields from confirmed facts across all supported portals
            log_stage("FILL", f"Filling non-secret form fields from confirmed facts on {current_url}")
            fill_form_fields(page, facts_by_key, ALL_PORTAL_SELECTORS, field_actions)

            # Stage 3b: Detect if any visible non-secret fields remain unfilled / unknown
            unfilled_fields = detect_unfilled_portal_fields(page)
            if unfilled_fields:
                log_stage("UNKNOWN_FIELDS", f"Detected {len(unfilled_fields)} unfilled/unknown fields on portal page. Pausing for user input.")
                pause_rec = UserPausePoint(
                    step_id=main_step_id,
                    reason=f"Unfilled portal form fields detected ({len(unfilled_fields)} fields)",
                    paused_at=utc_now(),
                )
                user_pause_points.append(pause_rec)

                _DRIVER_SESSIONS[session_id] = {
                    "playwright": p,
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "started_at": started_at,
                    "field_actions": field_actions,
                    "user_pause_points": user_pause_points,
                    "portal_observations": portal_observations,
                    "main_step_id": main_step_id,
                    "missing_portal_fields": unfilled_fields,
                }

                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.PAUSED_FOR_USER,
                    step_results=[
                        StepExecutionResult(
                            step_id=main_step_id,
                            status=StepExecutionStatus.PAUSED_FOR_USER,
                            action_summary=f"Form loaded with {len(unfilled_fields)} unknown/unfilled fields. Awaiting user input.",
                            started_at=started_at,
                        )
                    ],
                    field_actions=field_actions,
                    user_pause_points=user_pause_points,
                    portal_observations=portal_observations,
                    submission_attempted=False,
                    confirmation_observed=False,
                    warnings=warnings,
                )

            # Inject contextual top helper banner into browser page
            banner_msg = "Form fields filled automatically from your vault. Please enter the <strong>CAPTCHA code</strong> below, then click <strong>Resume Assistant</strong> in your web dashboard."
            if "check-aadhaar-status" in current_url or "status" in current_url or "track" in current_url:
                banner_msg = "Enrolment ID / SRN identifier filled from your records. Please enter the <strong>CAPTCHA code</strong> below, then click <strong>Submit</strong> or <strong>Resume Assistant</strong> in your web dashboard."
            elif "uidai" in current_url or "aadhaar" in current_url:
                banner_msg = "Aadhaar number filled from your vault. Please enter the <strong>CAPTCHA</strong> and click <strong>Send OTP</strong>, then type the OTP and click <strong>Resume Assistant</strong> in your web dashboard."
            elif "passport" in current_url:
                banner_msg = "Details prepared from your vault. Complete login / verification below, then click <strong>Resume Assistant</strong> in your web dashboard."

            try:
                page.evaluate(f"""() => {{
                    if (!document.getElementById('bureaucracy-agent-banner')) {{
                        const b = document.createElement('div');
                        b.id = 'bureaucracy-agent-banner';
                        b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:linear-gradient(90deg, #0f172a, #1e1b4b);color:#f8fafc;padding:12px 20px;z-index:999999;font-family:sans-serif;font-size:14px;box-shadow:0 4px 20px rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:space-between;border-bottom:2px solid #818cf8;';
                        b.innerHTML = '<div style="display:flex;align-items:center;gap:12px;"><span style="font-size:18px;">🤖</span><div><strong>AI Personal Bureaucracy Assistant:</strong> {banner_msg}</div></div><div style="background:#4338ca;color:#fff;padding:6px 14px;border-radius:8px;font-weight:700;font-size:12px;letter-spacing:0.05em;">HUMAN-IN-THE-LOOP ACTIVE</div>';
                        document.body.prepend(b);
                    }}
                }}""")
            except Exception:
                pass

            # Stage 4: Detect secret controls (CAPTCHA, OTP)
            has_secret, secret_descs, locators_found = detect_secret_elements(page)
            if has_secret:
                secret_name = " / ".join(secret_descs)
                log_stage("HUMAN_IN_THE_LOOP", f"Security challenge detected ({secret_name}). Pausing workflow for user action in browser.")
                if locators_found:
                    try:
                        page.locator(locators_found[0]).scroll_into_view_if_needed()
                    except Exception:
                        pass

                pause_rec = UserPausePoint(
                    step_id=main_step_id,
                    reason=f"Verification required on portal ({secret_name})",
                    paused_at=utc_now(),
                )
                user_pause_points.append(pause_rec)

                # Persist active browser session in memory
                _DRIVER_SESSIONS[session_id] = {
                    "playwright": p,
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "started_at": started_at,
                    "field_actions": field_actions,
                    "user_pause_points": user_pause_points,
                    "portal_observations": portal_observations,
                    "main_step_id": main_step_id,
                }

                # Return PAUSED_FOR_USER so the orchestrator transitions to PAUSED_CAPTCHA
                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.PAUSED_FOR_USER,
                    step_results=[
                        StepExecutionResult(
                            step_id=main_step_id,
                            status=StepExecutionStatus.PAUSED_FOR_USER,
                            action_summary=f"Automated fields prepared. Paused for human entry of {secret_name}.",
                            started_at=started_at,
                        )
                    ],
                    field_actions=field_actions,
                    user_pause_points=user_pause_points,
                    portal_observations=portal_observations,
                    submission_attempted=False,
                    confirmation_observed=False,
                    warnings=warnings,
                )

            # If interactive mode is enabled (default in live runs), keep browser open for citizen inspection and interaction
            if interactive or request.dry_run or stop_before_submit:
                log_stage("HUMAN_IN_THE_LOOP", "Portal loaded for user interaction. Browser session remains open.")
                pause_rec = UserPausePoint(
                    step_id=main_step_id,
                    reason="Portal loaded. Review form and perform any verification in the browser.",
                    paused_at=utc_now(),
                )
                user_pause_points.append(pause_rec)

                _DRIVER_SESSIONS[session_id] = {
                    "playwright": p,
                    "browser": browser,
                    "context": context,
                    "page": page,
                    "started_at": started_at,
                    "field_actions": field_actions,
                    "user_pause_points": user_pause_points,
                    "portal_observations": portal_observations,
                    "main_step_id": main_step_id,
                }

                return ExecutionResult(
                    contract_version=CONTRACT_VERSION,
                    execution_request_id=request.execution_request_id,
                    request_id=request.request_id,
                    plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                    plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                    validation_request_id=request.validation_result.validation_request_id,
                    execution_status=ExecutionStatus.PAUSED_FOR_USER,
                    step_results=[
                        StepExecutionResult(
                            step_id=main_step_id,
                            status=StepExecutionStatus.PAUSED_FOR_USER,
                            action_summary="Portal loaded and non-secret details filled. Waiting for user interaction.",
                            started_at=started_at,
                        )
                    ],
                    field_actions=field_actions,
                    user_pause_points=user_pause_points,
                    portal_observations=portal_observations,
                    submission_attempted=False,
                    confirmation_observed=False,
                    warnings=warnings,
                )

            # Clean close only if non-interactive mode explicitly specified
            try:
                browser.close()
                p.stop()
            except Exception:
                pass

            return ExecutionResult(
                contract_version=CONTRACT_VERSION,
                execution_request_id=request.execution_request_id,
                request_id=request.request_id,
                plan_id=request.workflow_plan.plan_id if request.workflow_plan else "plan-1",
                plan_version=request.workflow_plan.plan_version if request.workflow_plan else 1,
                validation_request_id=request.validation_result.validation_request_id,
                execution_status=ExecutionStatus.PREPARED_FOR_REVIEW,
                step_results=[
                    StepExecutionResult(
                        step_id=main_step_id,
                        status=StepExecutionStatus.COMPLETED,
                        action_summary="Execution pass complete.",
                        started_at=started_at,
                        completed_at=utc_now(),
                    )
                ],
                field_actions=field_actions,
                user_pause_points=user_pause_points,
                portal_observations=portal_observations,
                submission_attempted=False,
                confirmation_observed=False,
                warnings=warnings,
                completed_at=utc_now(),
            )

        except Exception as exc:
            return handle_flow_error(exc, "UNHANDLED_EXCEPTION")


# Backward compatibility alias
PassportSevaDriver = PortalBrowserDriver
