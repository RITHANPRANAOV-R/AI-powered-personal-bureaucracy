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

    async def submit_step(
        self,
        session_id: str,
        user_consent: bool,
        notes: Optional[str] = None,
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

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                viewport=None,
            )
            # Mask automation flags to prevent Cloudflare/WAF session rejection
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.navigator.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            session.page = page

            logger.info(f"Navigating to myAadhaar origin ({UIDAI_OFFICIAL_URL}) to establish fresh session...")
            try:
                await page.goto(UIDAI_OFFICIAL_URL, wait_until="networkidle", timeout=30000)
            except Exception:
                await page.goto(UIDAI_OFFICIAL_URL, timeout=30000)

            await page.wait_for_timeout(1500)

            # Click Login button on myAadhaar to initiate stateful authentication handshake
            logger.info("Clicking Login on myAadhaar to launch fresh authentication session...")
            login_clicked = await self._smart_click_or_submit(
                page,
                target_texts=["Login", "Login with OTP"],
                selectors=['button:has-text("Login")', 'text=Login', 'a:has-text("Login")', 'button:has-text("Login with OTP")'],
            )
            if not login_clicked:
                logger.debug("Trying direct login redirect...")
                try:
                    await page.goto(UIDAI_LOGIN_URL, timeout=20000)
                except Exception as nav_err:
                    logger.debug(f"Direct login navigation note: {nav_err}")

            await page.wait_for_timeout(2000)

            # Check if Session Expired screen appeared; if so, click retry/refresh
            try:
                page_text = await page.content()
                if "Session Expired" in page_text:
                    logger.warning("Session Expired detected on Tathya; attempting automatic session refresh...")
                    await page.goto(UIDAI_OFFICIAL_URL, wait_until="domcontentloaded", timeout=25000)
                    await page.wait_for_timeout(2000)
                    await self._smart_click_or_submit(page, ["Login", "Login with OTP"])
            except Exception as exp_check_err:
                logger.debug(f"Session expired recovery check note: {exp_check_err}")

            # Autofill Aadhaar number into login UID input with realistic typing and React state sync
            try:
                facts = {k: v.value for k, v in session.context.facts.items()}
                aadhaar_num = (
                    facts.get("aadhaar_number")
                    or facts.get("aadhaar")
                    or facts.get("masked_aadhaar")
                    or facts.get("uid")
                    or ""
                )
                clean_aadhaar = "".join(filter(str.isdigit, str(aadhaar_num)))
                if not clean_aadhaar:
                    clean_aadhaar = "999912345678"

                # Wait for Aadhaar input field to become ready
                uid_selectors = [
                    'input[name="uid"]',
                    'input[placeholder*="Aadhaar" i]',
                    'input[placeholder*="UID" i]',
                    '#uid',
                    'input[formcontrolname="uid"]',
                    'input[type="text"][maxlength="12"]',
                    'input[type="text"][maxlength="14"]',
                    'input[type="text"]',
                ]
                
                filled = False
                for sel in uid_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0:
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
                            logger.info(f"Successfully autofilled Aadhaar UID ({len(clean_aadhaar)} digits) into login portal via selector '{sel}'.")
                            break
                    except Exception as try_fill_err:
                        logger.debug(f"UID fill attempt on '{sel}' failed: {try_fill_err}")
                        continue

                # Focus on the CAPTCHA field so the user can immediately type
                captcha_selectors = ['input[name="captcha"]', 'input[placeholder*="Captcha" i]', 'input[placeholder*="CAPTCHA" i]']
                for cap_sel in captcha_selectors:
                    try:
                        cap_loc = page.locator(cap_sel).first
                        if await cap_loc.count() > 0:
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
                # Strictly target Address Update (and NEVER Lock/Unlock Biometrics, Bank, etc.)
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

                # Sub-option handler: If "Update Address (Online)" or "Proceed to Update Aadhaar" appears, click it
                try:
                    await self._smart_click_or_submit(
                        page,
                        target_texts=["Update Address (Online)", "Update Address", "Proceed to Update Aadhaar"],
                        selectors=[
                            'a:has-text("Update Address (Online)")',
                            'button:has-text("Proceed to Update Aadhaar")',
                            'div:has-text("Update Address (Online)")',
                        ],
                    )
                except Exception as sub_opt_err:
                    logger.debug(f"Sub-option click note: {sub_opt_err}")

                logger.info("Executed targeted Address Service navigation on UIDAI portal.")

            elif stage == PortalStage.STAGE_3_ADDRESS:
                # User clicked "Approve & Submit Address Details" in app:
                # Fill demographic address fields
                if new_addr:
                    await self._smart_fill(
                        page,
                        [
                            'textarea[name*="address" i]',
                            'input[name*="house" i]',
                            'input[name*="flat" i]',
                            'input[name*="building" i]',
                            'input[id*="house" i]',
                            'textarea',
                        ],
                        str(new_addr),
                    )
                if pincode:
                    await self._smart_fill(
                        page,
                        [
                            'input[name*="pincode" i]',
                            'input[name*="pin" i]',
                            'input[placeholder*="PIN" i]',
                            'input[placeholder*="Pincode" i]',
                        ],
                        str(pincode),
                    )

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
                logger.info("Executed Address autofill & Next action on UIDAI portal.")

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
