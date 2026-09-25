"""Selector map and navigation targets for RTI Online form."""

from __future__ import annotations

from typing import Any, Dict, List

# Primary URLs for RTI Online
RTI_REGISTRATION_URLS: List[str] = [
    "https://rtionline.gov.in/guidelines.php?request",
    "https://rtionline.gov.in/",
    "https://www.rtionline.gov.in/",
]

REGISTRATION_URLS: List[str] = RTI_REGISTRATION_URLS

# RTI Online Guidelines Page Locators
RTI_GUIDELINES_SELECTORS: Dict[str, Any] = {
    "checkbox": {
        "locators": [
            "input[name='CHECKBOX_1']",
            "input[type='checkbox']",
            "input#chk",
        ]
    },
    "submit_button": {
        "locators": [
            "input[type='submit'][value='Submit']",
            "input[name='submit']",
            "input[value='Submit']",
        ]
    },
}

# RTI Online Request Form Locators
RTI_FORM_SELECTORS: Dict[str, Dict[str, Any]] = {
    "email": {
        "type": "input",
        "labels": ["Email ID", "Email"],
        "locators": ["input[name='Email']", "input[id='Email']", "input#email"],
        "profile_key": "email",
        "is_secret": False,
    },
    "cell": {
        "type": "input",
        "labels": ["Mobile Number"],
        "locators": ["input[name='cell']", "input[id='cell']", "input#mobile"],
        "profile_key": "mobile",
        "is_secret": False,
    },
    "name": {
        "type": "input",
        "labels": ["Name"],
        "locators": ["input[name='name']", "input[id='name']", "input[name='full_name']"],
        "profile_key": "full_name",
        "is_secret": False,
    },
    "address": {
        "type": "textarea",
        "labels": ["Address"],
        "locators": ["textarea[name='address']", "input[name='address']", "textarea#address"],
        "profile_key": "present_address",
        "is_secret": False,
    },
    "pincode": {
        "type": "input",
        "labels": ["Pincode"],
        "locators": ["input[name='pincode']", "input[id='pincode']"],
        "profile_key": "pincode",
        "is_secret": False,
    },
    "state": {
        "type": "select",
        "labels": ["State"],
        "locators": ["select[name='state']", "select[id='state']"],
        "profile_key": "state",
        "is_secret": False,
    },
    "gender": {
        "type": "select",
        "labels": ["Gender"],
        "locators": ["select[name='gender']", "input[name='gender']"],
        "profile_key": "gender",
        "is_secret": False,
    },
    "rti_text": {
        "type": "textarea",
        "labels": ["Text for RTI Request Application"],
        "locators": ["textarea[name='text']", "textarea[name='rti_text']", "textarea#rti_text"],
        "profile_key": "rti_request_text",
        "is_secret": False,
    },
    # Secret / CAPTCHA fields (NEVER AUTO-FILLED)
    "captcha_image": {
        "type": "img",
        "labels": ["CAPTCHA Image"],
        "locators": ["img#captchaimg", "img[src*='captcha']", "img[src*='captcha_code_file']"],
        "is_secret": True,
    },
    "captcha_input": {
        "type": "input",
        "labels": ["Enter CAPTCHA Code"],
        "locators": ["input[name='6_letters_code']", "input[id='6_letters_code']", "input[name='captchaText']"],
        "is_secret": True,
    },
    # Submit Button
    "submit_button": {
        "type": "button",
        "labels": ["Submit"],
        "locators": [
            "input[name='Submit']",
            "input[id='Status']",
            "input[type='submit'][value='Submit']",
            "button[type='submit']",
        ],
    },
}

REGISTRATION_SELECTORS = RTI_FORM_SELECTORS
