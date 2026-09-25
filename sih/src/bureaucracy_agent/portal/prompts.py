"""Terminal prompts and banners for interactive human-in-the-loop steps."""

SECURITY_PAUSE_BANNER = """
================================================================================
                    SECURITY PAUSE: HUMAN ACTION REQUIRED
================================================================================
The browser has opened the official RTI Online submit request page.
Please switch to the visible browser window and complete:
  - CAPTCHA challenge

The assistant will NEVER type into CAPTCHA, OTP, or password fields.
Once you have entered the CAPTCHA in the browser window, press ENTER below to resume.
================================================================================
"""

REVIEW_CHECKPOINT_HEADER = """
================================================================================
                      FORM REVIEW CHECKPOINT
================================================================================
Review all non-secret form fields prepared by the assistant:
"""

REVIEW_CHECKPOINT_FOOTER = """
================================================================================
Review the browser window now.
To authorize the assistant to click submit on the official portal page,
you MUST type the exact submission confirmation phrase:

  CONFIRM SUBMISSION

Any other text or pressing ENTER without typing the exact phrase will CANCEL.
================================================================================
"""

PAYMENT_PAUSE_BANNER = """
================================================================================
                    PAYMENT PAUSE: OFFICIAL PORTAL PAYMENT
================================================================================
Payment is required on the official portal.
Please complete the payment directly in the official browser window interface.
The assistant will wait and NEVER access bank, card, or UPI details.

Once payment is complete and you return to the confirmation page, press ENTER.
================================================================================
"""
