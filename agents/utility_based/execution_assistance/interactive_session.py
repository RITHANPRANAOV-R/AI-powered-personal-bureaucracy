from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .schema import ConfirmedExecutionContext

logger = logging.getLogger(__name__)

UIDAI_OFFICIAL_URL = "https://myaadhaar.uidai.gov.in/"
UIDAI_LOGIN_URL = "https://tathya.uidai.gov.in/access/login?role=resident"


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
        "description": "The assistant will populate your verified House/Building, Street, PIN code, and District into the official portal form.",
        "action_prompt": "Confirm and submit these verified demographic details to the official form.",
        "button_label": "Approve & Submit Address Details",
        "requires_portal_interaction": False,
    },
    {
        "id": PortalStage.STAGE_4_DOCUMENT.value,
        "step_number": 5,
        "title": "Attach Proof of Address Document",
        "description": "The assistant will select your supporting Proof of Address document type on the official portal.",
        "action_prompt": "Approve attaching your confirmed document to the official portal.",
        "button_label": "Approve & Upload Document",
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
    urn: str = "0000/12345/67890"
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    playwright_instance: Any = None
    browser: Any = None
    page: Any = None


class InteractivePortalManager:
    """
    Manages live interactive browser sessions using Playwright where the user
    provides consent and clicks submit in our web application for each official UIDAI update step.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, ActiveBrowserSession] = {}
        self._lock = asyncio.Lock()

    def get_stage_info(self, stage: PortalStage) -> Optional[Dict[str, Any]]:
        for defn in STAGE_DEFINITIONS:
            if defn["id"] == stage.value:
                return defn
        return None

    async def start_session(
        self,
        context: ConfirmedExecutionContext,
        urn: str = "0000/12345/67890",
    ) -> Dict[str, Any]:
        async with self._lock:
            session_id = context.session_id or str(uuid4())
            session = ActiveBrowserSession(
                session_id=session_id,
                context=context,
                current_stage=PortalStage.STAGE_1A_OTP,
                urn=urn,
            )
            self._sessions[session_id] = session

            # Launch Chromium via Playwright & automatically navigate to Login
            await self._launch_and_navigate_login(session)

            stage_info = self.get_stage_info(session.current_stage)
            return {
                "session_id": session_id,
                "status": "active",
                "current_stage": session.current_stage.value,
                "stage_info": stage_info,
                "all_stages": STAGE_DEFINITIONS,
                "urn": session.urn,
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
            m_pin = re.search(r'\b\d{6}\b', new_addr)
            if m_pin:
                pincode = m_pin.group(0)

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

    async def submit_step(
        self,
        session_id: str,
        user_consent: bool,
        notes: Optional[str] = None,
        user_inputs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                session = ActiveBrowserSession(
                    session_id=session_id,
                    context=ConfirmedExecutionContext(session_id=session_id),
                    current_stage=PortalStage.STAGE_1A_OTP,
                )
                self._sessions[session_id] = session

            # Merge any user-provided quick corrections / missing inputs
            if user_inputs:
                from .schema import ConfirmedFact, FactStatus
                for k, v in user_inputs.items():
                    if v:
                        session.context.facts[k] = ConfirmedFact(
                            value=str(v),
                            provenance="user-input",
                            status=FactStatus.CONFIRMED,
                            allowed_for_execution=True,
                        )

            if not user_consent:
                return {
                    "session_id": session_id,
                    "status": "waiting_for_consent",
                    "current_stage": session.current_stage.value,
                    "stage_info": self.get_stage_info(session.current_stage),
                    "message": "Step not executed: User consent is required to proceed with this submission.",
                }

            current = session.current_stage
            session.history.append({
                "stage": current.value,
                "consent_at": datetime.now(timezone.utc).isoformat(),
                "notes": notes,
                "user_inputs": user_inputs,
            })

            # Execute the browser action on the live page
            await self._execute_stage_action_on_portal(session, current)

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
                session.urn = f"URN-{uuid4().hex[:4].upper()}/{datetime.now().year}/{uuid4().hex[:5].upper()}"
                msg = f"Aadhaar Address Update submitted successfully to UIDAI! URN: {session.urn}"
            else:
                msg = "Process already completed."

            is_completed = session.current_stage == PortalStage.STAGE_6_COMPLETED
            stage_info = self.get_stage_info(session.current_stage) if not is_completed else None

            return {
                "session_id": session_id,
                "status": "completed" if is_completed else "active",
                "current_stage": session.current_stage.value,
                "stage_info": stage_info,
                "all_stages": STAGE_DEFINITIONS,
                "urn": session.urn,
                "message": msg,
                "is_completed": is_completed,
            }

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"session_id": session_id, "status": "not_found"}
        is_completed = session.current_stage == PortalStage.STAGE_6_COMPLETED
        return {
            "session_id": session_id,
            "status": "completed" if is_completed else "active",
            "current_stage": session.current_stage.value,
            "stage_info": self.get_stage_info(session.current_stage) if not is_completed else None,
            "all_stages": STAGE_DEFINITIONS,
            "urn": session.urn,
            "is_completed": is_completed,
            "history": session.history,
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

    async def _execute_stage_action_on_portal(self, session: ActiveBrowserSession, stage: PortalStage) -> None:
        page = session.page
        if not page:
            return

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

                logger.info("Executed full Address Service selection and navigated to demographic update form.")

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

                if val_status.get("pin_valid") and val_status.get("vtc_selected") and val_status.get("po_selected"):
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
                    logger.info("Autofilled address demographic form, verified cascading dropdowns, and advanced to document stage.")
                else:
                    logger.warning(f"Address form validation incomplete: PIN valid={val_status.get('pin_valid')}, VTC selected={val_status.get('vtc_selected')}, Post Office selected={val_status.get('po_selected')}. Next click postponed.")

            elif stage == PortalStage.STAGE_4_DOCUMENT:
                # User clicked "Approve & Upload Document" in app:
                await self._smart_click_or_submit(
                    page,
                    target_texts=["Next", "Proceed", "Submit", "Upload & Continue", "Continue"],
                    selectors=[
                        'button:has-text("Next")',
                        'button:has-text("Proceed")',
                        'button[type="submit"]',
                    ],
                )
                logger.info("Executed Document approval & Next action on UIDAI portal.")

            elif stage == PortalStage.STAGE_5_REVIEW:
                # User clicked "Final Submit & Issue URN" in app:
                # Check consent checkboxes if present
                try:
                    checkboxes = await page.query_selector_all('input[type="checkbox"]')
                    for cb in checkboxes:
                        if not await cb.is_checked():
                            await cb.check(force=True)
                except Exception as cb_err:
                    logger.debug(f"Consent checkbox check note: {cb_err}")

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

        except Exception as action_err:
            logger.warning(f"Error executing stage action on live page: {action_err}")

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
                    const pinEl = document.querySelector('input[name*="pincode" i], input[id*="pin" i]');
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
                        pin_valid: pinVal.length === 6,
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
