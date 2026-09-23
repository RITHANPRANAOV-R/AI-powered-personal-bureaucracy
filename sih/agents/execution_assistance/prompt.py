"""Execution & Assistance Agent Rationale and Policy Documentation.

Why Python Playwright and Accessible Locators are used instead of a Generative LLM:
----------------------------------------------------------------------------------
1. **Deterministic & Inspectable Browser Control**: Web page automation (navigation, field entry,
   form validation, and clicking Submit) must be predictable, auditable, and strictly gated by code.
   A generative LLM must NEVER be given direct control over browser locators, form field inputs,
   or submission actions.
2. **Preventing Hallucinations & Unapproved Actions**: LLMs can misidentify form fields, invent input
   data, hallucinate element selectors, or click buttons out of sequence.
3. **Strict Credential & Secret Boundary**: Passwords, OTPs, CAPTCHAs, recovery codes, and payment
   details are NEVER read, typed, stored, or logged by any agent. Visible browser execution allows
   the automation loop to pause deterministically, allowing the human user to complete authentication
   challenges manually in the open browser window.
4. **Exact Terminal Approval Gate**: Form submission is gated by an explicit terminal prompt requiring
   the user to inspect the visible browser window and type the exact string `SUBMIT PASSPORT SEVA REGISTRATION`.
5. **No-Retry / Single-Click Enforcement**: To prevent accidental duplicate form submissions or account
   creation attempts, the pre-click state `submission_attempted = True` is persisted prior to clicking.
   If an outcome is ambiguous or times out, the status is set to `uncertain`, and auto-retry is prohibited.
"""

SYSTEM_DESIGN_DOCUMENTATION = __doc__
