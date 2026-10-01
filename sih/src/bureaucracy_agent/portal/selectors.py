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
    "ministry": {
        "type": "select",
        "labels": ["Public Authority / Ministry / Department"],
        "locators": [
            "select[name='ministry']",
            "select[id='ministry']",
            "select[name='dept']",
            "select[id='dept']",
            "select[name='sub_dept']",
            "select[id='sub_dept']",
            "select[name='public_authority']",
        ],
        "profile_key": "ministry",
        "is_secret": False,
    },
    "country": {
        "type": "select",
        "labels": ["Country"],
        "locators": ["select[name='country']", "select[id='country']"],
        "profile_key": "country",
        "default": "India",
        "is_secret": False,
    },
    "status": {
        "type": "select",
        "labels": ["Status (Rural / Urban)"],
        "locators": ["select[name='edu_status']", "select[name='status']", "select[id='status']"],
        "profile_key": "status",
        "default": "Urban",
        "is_secret": False,
    },
    "educational_status": {
        "type": "select",
        "labels": ["Educational Status"],
        "locators": ["select[name='edu_level']", "select[name='education']", "select[id='edu_level']"],
        "profile_key": "educational_status",
        "default": "Literate",
        "is_secret": False,
    },
    "phone": {
        "type": "input",
        "labels": ["Phone Number"],
        "locators": ["input[name='phone']", "input[id='phone']", "input[name='tel']"],
        "profile_key": "phone",
        "is_secret": False,
    },
    "citizenship": {
        "type": "select",
        "labels": ["Citizenship"],
        "locators": ["select[name='citizenship']", "select[id='citizenship']"],
        "profile_key": "citizenship",
        "default": "Indian",
        "is_secret": False,
    },
    "bpl": {
        "type": "select",
        "labels": ["Is Requester Below Poverty Line?"],
        "locators": ["select[name='bpl']", "select[id='bpl']", "input[name='bpl']"],
        "profile_key": "bpl",
        "default": "No",
        "is_secret": False,
    },
    "rti_text": {
        "type": "textarea",
        "labels": ["Text for RTI Request Application"],
        "locators": [
            "textarea[name='text']",
            "textarea[name='rti_text']",
            "textarea#rti_text",
            "textarea[name='request_text']",
            "textarea#text",
        ],
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
        "locators": ["input[name='6_letters_code']", "input[id='6_letters_code']", "input[name='captchaText']", "input[name='captcha']"],
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
            "input[type='submit'][value='Proceed']",
            "input[type='submit'][value='Verify']",
            "input[type='submit']",
            "button[type='submit']",
        ],
    },
}

# UIDAI myAadhaar Portal Locators
AADHAAR_FORM_SELECTORS: Dict[str, Dict[str, Any]] = {
    "enrolment_id_or_srn": {
        "type": "input",
        "labels": ["Enrolment ID / SRN / URN", "Enter Enrolment ID, SRN or URN", "EID / SRN / URN"],
        "locators": [
            "input[name='eid']",
            "input[name='srn']",
            "input[name='urn']",
            "input[name='eidSrnUrn']",
            "input[name='enrolmentNumber']",
            "input[id*='eid']",
            "input[id*='srn']",
            "input[id*='urn']",
            "input[placeholder*='Enrolment']",
            "input[placeholder*='SRN']",
            "input[placeholder*='URN']",
            "input[placeholder*='Enter Enrolment']",
            "input[placeholder*='Service Request']",
            "input[placeholder*='Enter SRN']",
            "input[placeholder*='Enter URN']",
            "input[maxlength='28']",
            "input[maxlength='14']",
        ],
        "profile_key": "srn",
        "is_secret": False,
    },
    "aadhaar_number": {
        "type": "input",
        "labels": ["Aadhaar Number", "Enter Aadhaar Number"],
        "locators": [
            "input[name='uid']",
            "input[name='aadhaar']",
            "input[id*='aadhaar']",
            "input[placeholder*='Enter Aadhaar']",
            "input[placeholder*='Aadhaar']",
            "input[name='uidNumber']",
            "input[name='aadhaarNumber']",
            "input[maxlength='12']",
        ],
        "profile_key": "aadhaar_number",
        "is_secret": False,
    },
    "name": {
        "type": "input",
        "labels": ["Name", "Resident Name"],
        "locators": [
            "input[name='name']",
            "input[id='name']",
            "input[name='residentName']",
            "input[placeholder*='Name']",
            "input[placeholder*='Resident Name']",
        ],
        "profile_key": "full_name",
        "is_secret": False,
    },
    "mobile": {
        "type": "input",
        "labels": ["Mobile Number"],
        "locators": [
            "input[name='mobile']",
            "input[id='mobile']",
            "input[name='cell']",
            "input[placeholder*='Mobile']",
        ],
        "profile_key": "mobile",
        "is_secret": False,
    },
    "email": {
        "type": "input",
        "labels": ["Email ID"],
        "locators": [
            "input[name='email']",
            "input[id='email']",
            "input[placeholder*='Email']",
        ],
        "profile_key": "email",
        "is_secret": False,
    },
    "pincode": {
        "type": "input",
        "labels": ["Pincode"],
        "locators": [
            "input[name='pincode']",
            "input[id='pincode']",
            "input[name='pin']",
            "input[placeholder*='Pincode']",
            "input[placeholder*='Pin']",
            "input[placeholder*='PIN']",
        ],
        "profile_key": "pincode",
        "is_secret": False,
    },
    "care_of": {
        "type": "input",
        "labels": ["Care of / Father Name"],
        "locators": [
            "input[name='careOf']",
            "input[id='careOf']",
            "input[name='co']",
            "input[placeholder*='Care of']",
            "input[placeholder*='C/O']",
        ],
        "profile_key": "father_name",
        "is_secret": False,
    },
    "house_no": {
        "type": "input",
        "labels": ["House / Building / Apartment"],
        "locators": [
            "input[name='houseNo']",
            "input[id='houseNo']",
            "input[name='building']",
            "input[placeholder*='House']",
            "input[placeholder*='Building']",
            "input[placeholder*='Flat']",
        ],
        "profile_key": "present_address",
        "is_secret": False,
    },
    "street": {
        "type": "input",
        "labels": ["Street / Road / Lane"],
        "locators": [
            "input[name='street']",
            "input[id='street']",
            "input[name='road']",
            "input[placeholder*='Street']",
            "input[placeholder*='Road']",
        ],
        "profile_key": "present_address",
        "is_secret": False,
    },
    "landmark": {
        "type": "input",
        "labels": ["Landmark"],
        "locators": [
            "input[name='landmark']",
            "input[id='landmark']",
            "input[placeholder*='Landmark']",
        ],
        "profile_key": "present_address",
        "is_secret": False,
    },
    "area": {
        "type": "input",
        "labels": ["Area / Locality / Sector"],
        "locators": [
            "input[name='area']",
            "input[id='area']",
            "input[name='locality']",
            "input[placeholder*='Area']",
            "input[placeholder*='Locality']",
            "input[placeholder*='Sector']",
        ],
        "profile_key": "present_address",
        "is_secret": False,
    },
    "village_town_city": {
        "type": "select",
        "labels": ["Village / Town / City"],
        "locators": [
            "select[name='vtc']",
            "select[id='vtc']",
            "select[name='city']",
            "select[id='city']",
            "input[name='vtc']",
        ],
        "profile_key": "city",
        "is_secret": False,
    },
    "post_office": {
        "type": "select",
        "labels": ["Post Office"],
        "locators": [
            "select[name='postOffice']",
            "select[id='postOffice']",
            "select[name='po']",
            "input[name='postOffice']",
        ],
        "profile_key": "city",
        "is_secret": False,
    },
    "district": {
        "type": "select",
        "labels": ["District"],
        "locators": [
            "select[name='district']",
            "select[id='district']",
            "input[name='district']",
        ],
        "profile_key": "district",
        "is_secret": False,
    },
    "state": {
        "type": "select",
        "labels": ["State"],
        "locators": [
            "select[name='state']",
            "select[id='state']",
            "input[name='state']",
        ],
        "profile_key": "state",
        "is_secret": False,
    },
    # Secret verification locators
    "captcha_image": {
        "type": "img",
        "labels": ["CAPTCHA Image"],
        "locators": [
            "img#captchaimg",
            "img[src*='captcha']",
            "img[src*='security']",
            "img.captcha-image",
            "div.captcha-img img",
        ],
        "is_secret": True,
    },
    "captcha_input": {
        "type": "input",
        "labels": ["Enter CAPTCHA Code"],
        "locators": [
            "input[name='captcha']",
            "input[id='captcha']",
            "input[placeholder*='Captcha']",
            "input[placeholder*='CAPTCHA']",
            "input[placeholder*='Security Code']",
            "input[name='securityCode']",
        ],
        "is_secret": True,
    },
    "otp_input": {
        "type": "input",
        "labels": ["Enter OTP"],
        "locators": [
            "input[name='otp']",
            "input[id='otp']",
            "input[placeholder*='Enter OTP']",
            "input[placeholder*='OTP']",
            "input[maxlength='6']",
        ],
        "is_secret": True,
    },
}

# Union dictionary of all supported government form selectors
ALL_PORTAL_SELECTORS: Dict[str, Dict[str, Any]] = {
    **RTI_FORM_SELECTORS,
    **AADHAAR_FORM_SELECTORS,
}

REGISTRATION_SELECTORS = ALL_PORTAL_SELECTORS
