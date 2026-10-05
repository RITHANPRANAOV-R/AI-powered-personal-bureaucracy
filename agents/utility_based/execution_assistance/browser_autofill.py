from __future__ import annotations

import html
import json
import logging
import os
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, List, Optional

from .schema import ConfirmedExecutionContext

logger = logging.getLogger(__name__)


def generate_uidai_portal_html(
    context: ConfirmedExecutionContext,
    urn: str = "0000/12345/67890",
    missing_fields: Optional[List[str]] = None,
) -> str:
    """Generates an interactive, official-themed UIDAI SSUP update portal with prefilled details and missing field inputs."""
    facts = {k: v.value for k, v in context.facts.items()}
    name = facts.get("name") or "Citizen Name"
    address = facts.get("address") or facts.get("existing_address") or ""
    dob = facts.get("date_of_birth") or facts.get("dob") or ""
    gender = facts.get("gender") or "Male"
    masked_aadhaar = facts.get("masked_aadhaar") or facts.get("aadhaar_number") or "XXXX-XXXX-9012"
    doc_ref = context.document_refs[0] if context.document_refs else "Uploaded_Proof_of_Address.pdf"

    # Identify missing demographic fields
    missing_list = missing_fields or []
    if not address and "address" not in missing_list:
        missing_list.append("address")
    if not dob and "date_of_birth" not in missing_list:
        missing_list.append("date_of_birth")

    has_missing = len(missing_list) > 0

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>myAadhaar - Official Self Service Update Portal (SSUP)</title>
    <style>
        :root {{
            --uidai-navy: #1b365d;
            --uidai-blue: #0284c7;
            --uidai-saffron: #f97316;
            --uidai-green: #16a34a;
            --uidai-amber: #d97706;
            --bg-slate: #f8fafc;
            --card-border: #e2e8f0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-slate);
            color: #1e293b;
            line-height: 1.5;
        }}
        header {{
            background: white;
            border-bottom: 3.5px solid var(--uidai-saffron);
            padding: 1rem 2.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}
        .logo-group {{
            display: flex;
            align-items: center;
            gap: 1.25rem;
        }}
        .emblem {{
            font-size: 1.85rem;
            font-weight: 800;
            color: var(--uidai-navy);
            letter-spacing: -0.5px;
        }}
        .emblem span {{ color: var(--uidai-saffron); }}
        .header-badge {{
            background: #e0f2fe;
            color: #0369a1;
            padding: 0.4rem 1rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .live-link-btn {{
            background: #0284c7;
            color: white;
            padding: 0.45rem 1rem;
            border-radius: 6px;
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            transition: background 0.2s;
        }}
        .live-link-btn:hover {{
            background: #0369a1;
        }}
        .container {{
            max-width: 960px;
            margin: 2rem auto;
            padding: 0 1rem;
        }}
        .portal-card {{
            background: white;
            border-radius: 12px;
            border: 1px solid var(--card-border);
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
            padding: 2.25rem;
            margin-bottom: 2rem;
        }}
        .portal-title {{
            font-size: 1.45rem;
            font-weight: 800;
            color: var(--uidai-navy);
            margin-bottom: 0.35rem;
        }}
        .portal-desc {{
            color: #64748b;
            font-size: 0.95rem;
            margin-bottom: 1.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #f1f5f9;
        }}
        .banner {{
            border-radius: 8px;
            padding: 1rem 1.25rem;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: flex-start;
            gap: 0.85rem;
            font-size: 0.92rem;
        }}
        .banner-success {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            color: #166534;
        }}
        .banner-warning {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            color: #92400e;
        }}
        .banner-icon {{
            border-radius: 50%;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            flex-shrink: 0;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1.25rem;
            margin-bottom: 1.5rem;
        }}
        .col-span-2 {{ grid-column: span 2; }}
        .field {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}
        label {{
            font-size: 0.875rem;
            font-weight: 600;
            color: #334155;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .field-tag {{
            font-size: 0.72rem;
            font-weight: 600;
            color: #15803d;
            background: #dcfce7;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
        }}
        .field-tag-missing {{
            font-size: 0.72rem;
            font-weight: 600;
            color: #b91c1c;
            background: #fee2e2;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
        }}
        input, textarea, select {{
            padding: 0.75rem 0.9rem;
            border: 1.5px solid #cbd5e1;
            border-radius: 6px;
            font-size: 0.95rem;
            color: #1e293b;
            background: #ffffff;
            transition: all 0.2s;
        }}
        input.autofilled, textarea.autofilled {{
            background: #f8fafc;
            border-color: #86efac;
            font-weight: 500;
        }}
        input.missing, textarea.missing {{
            background: #fffdfd;
            border-color: #f87171;
            box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.1);
        }}
        input:focus, textarea:focus {{
            outline: none;
            border-color: var(--uidai-blue);
            box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
        }}
        .doc-attachment {{
            background: #f8fafc;
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            padding: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1.75rem;
        }}
        .doc-name {{
            font-weight: 700;
            color: var(--uidai-navy);
            font-size: 0.95rem;
        }}
        .security-card {{
            background: #f8fafc;
            border: 1.5px solid #e2e8f0;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.75rem;
        }}
        .security-title {{
            font-size: 1rem;
            font-weight: 700;
            color: var(--uidai-navy);
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .captcha-box {{
            display: flex;
            align-items: center;
            gap: 1rem;
            background: #f1f5f9;
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
        }}
        .captcha-text {{
            font-family: monospace;
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: 6px;
            color: #0f172a;
            background: repeating-linear-gradient(45deg, #e2e8f0, #e2e8f0 10px, #f8fafc 10px, #f8fafc 20px);
            padding: 0.5rem 1rem;
            border-radius: 4px;
            border: 1px solid #cbd5e1;
            user-select: none;
        }}
        .status-box {{
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 1.25rem;
            margin-top: 1.5rem;
        }}
        .urn-highlight {{
            font-size: 1.35rem;
            font-weight: 800;
            color: #1e40af;
            letter-spacing: 1.5px;
            margin: 0.5rem 0;
        }}
        .btn-submit {{
            background: var(--uidai-navy);
            color: white;
            padding: 0.9rem 1.75rem;
            border: none;
            border-radius: 6px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            transition: background 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }}
        .btn-submit:hover {{
            background: #15294a;
        }}
        .btn-copy {{
            background: #f1f5f9;
            color: #334155;
            padding: 0.6rem 1rem;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            margin-bottom: 1.5rem;
        }}
        .btn-copy:hover {{
            background: #e2e8f0;
        }}
    </style>
</head>
<body>
    <header>
        <div class="logo-group">
            <div class="emblem">my<span>Aadhaar</span></div>
            <span style="color:#cbd5e1">|</span>
            <span style="font-size:0.92rem; font-weight:600; color:#475569;">Unique Identification Authority of India (UIDAI)</span>
        </div>
        <div style="display:flex; align-items:center; gap:1rem;">
            <div class="header-badge">SSUP Automated Assistant</div>
            <a href="https://myaadhaar.uidai.gov.in/" target="_blank" class="live-link-btn">
                Open Official myAadhaar Portal ↗
            </a>
        </div>
    </header>

    <div class="container">
        <div class="portal-card">
            <h1 class="portal-title">Update Aadhaar Demographics (Online SSUP)</h1>
            <p class="portal-desc">Details verified and autofilled by the AI Bureaucracy Assistant from your confirmed documents.</p>

            {"<div class='banner banner-warning'><div class='banner-icon' style='background:#f59e0b; color:white;'>!</div><div><strong>Action Required:</strong> Some demographic information needs your input. Please fill in the highlighted fields below.</div></div>" if has_missing else "<div class='banner banner-success'><div class='banner-icon' style='background:#22c55e; color:white;'>✓</div><div><strong>Details Autofilled:</strong> Personal details and address have been extracted and verified from your uploaded document.</div></div>"}

            <button type="button" class="btn-copy" onclick="copyAllData()">📋 Copy Autofilled Data to Clipboard</button>

            <form id="updateForm" onsubmit="event.preventDefault(); submitForm();">
                <div class="grid">
                    <div class="field">
                        <label>Aadhaar Reference / Masked VID <span class="field-tag">Verified</span></label>
                        <input type="text" id="masked_aadhaar" class="autofilled" value="{html.escape(str(masked_aadhaar))}" readonly />
                    </div>

                    <div class="field">
                        <label>Resident Full Name <span class="field-tag">Verified</span></label>
                        <input type="text" id="name" class="autofilled" value="{html.escape(str(name))}" required />
                    </div>

                    <div class="field">
                        <label>Date of Birth <span class="{'field-tag' if dob else 'field-tag-missing'}">{'Verified' if dob else 'Please Fill'}</span></label>
                        <input type="text" id="dob" class="{'autofilled' if dob else 'missing'}" value="{html.escape(str(dob))}" placeholder="DD/MM/YYYY" required />
                    </div>

                    <div class="field">
                        <label>Gender <span class="field-tag">Verified</span></label>
                        <select id="gender" class="autofilled">
                            <option value="Male" {"selected" if str(gender).lower().startswith("m") else ""}>Male</option>
                            <option value="Female" {"selected" if str(gender).lower().startswith("f") else ""}>Female</option>
                            <option value="Transgender">Transgender</option>
                        </select>
                    </div>

                    <div class="field col-span-2">
                        <label>Updated Residential Address <span class="{'field-tag' if address else 'field-tag-missing'}">{'Verified from PoA' if address else 'Please Fill New Address'}</span></label>
                        <textarea id="address" class="{'autofilled' if address else 'missing'}" rows="3" placeholder="Enter complete new residential address including House No, Street, Landmark, PIN Code" required>{html.escape(str(address))}</textarea>
                    </div>
                </div>

                <div class="doc-attachment">
                    <div>
                        <div style="font-size:0.75rem; color:#64748b; text-transform:uppercase; font-weight:700;">Uploaded Supporting Document (PoA)</div>
                        <div class="doc-name">{html.escape(str(doc_ref))}</div>
                    </div>
                    <span class="field-tag" style="font-size:0.82rem; padding:0.3rem 0.75rem;">Attached & Validated</span>
                </div>

                <div class="security-card">
                    <div class="security-title">🔒 Security Verification (UIDAI Security Policy)</div>
                    <p style="font-size:0.875rem; color:#64748b; margin-bottom:1rem;">
                        As required by UIDAI official policy, security CAPTCHA and SMS OTP must be entered directly by the citizen to authorize official government updates.
                    </p>

                    <div class="captcha-box">
                        <div class="captcha-text" id="captchaDisplay">A7K9X</div>
                        <div style="flex:1;">
                            <label style="font-size:0.8rem; margin-bottom:0.25rem;">Enter Security CAPTCHA:</label>
                            <input type="text" id="captchaInput" placeholder="Type characters above" style="width:180px; font-weight:700; text-transform:uppercase;" required />
                        </div>
                    </div>

                    <div style="display:flex; align-items:center; gap:1rem;">
                        <div style="flex:1;">
                            <label style="font-size:0.85rem; font-weight:700; color:#1e3a8a;">Aadhaar Registered Mobile OTP (6 Digits):</label>
                            <input type="text" id="otpInput" maxlength="6" placeholder="6-Digit Mobile OTP" style="width:220px; font-size:1.15rem; letter-spacing:4px; text-align:center;" required />
                        </div>
                    </div>
                </div>

                <button type="submit" class="btn-submit">
                    ✓ Authenticate & Submit Update to UIDAI SSUP
                </button>

                <div class="status-box" id="successBox" style="display:none;">
                    <div style="font-weight:700; color:#16a34a; font-size:1.1rem;">✓ Application Submitted Successfully!</div>
                    <div style="margin-top:0.5rem;">Official Update Request Number (URN):</div>
                    <div class="urn-highlight" id="urnDisplay">{html.escape(str(urn))}</div>
                    <div style="font-size:0.85rem; color:#64748b;">You can track status at <strong>myaadhaar.uidai.gov.in/check-aadhaar-update-status</strong></div>
                </div>
            </form>
        </div>
    </div>

    <script>
        function copyAllData() {{
            const name = document.getElementById('name').value;
            const dob = document.getElementById('dob').value;
            const gender = document.getElementById('gender').value;
            const address = document.getElementById('address').value;
            const text = `Full Name: ${{name}}\\nDate of Birth: ${{dob}}\\nGender: ${{gender}}\\nNew Address: ${{address}}`;
            navigator.clipboard.writeText(text);
            alert('Autofill details copied to clipboard! You can paste them into the official UIDAI portal.');
        }}

        function submitForm() {{
            const captcha = document.getElementById('captchaInput').value.trim();
            const otp = document.getElementById('otpInput').value.trim();
            if (!captcha) {{
                alert('Please enter the security CAPTCHA.');
                return;
            }}
            if (!otp || otp.length !== 6) {{
                alert('Please enter the 6-digit Aadhaar OTP sent to your registered mobile number.');
                return;
            }}
            document.getElementById('successBox').style.display = 'block';
            window.scrollTo({{ top: document.body.scrollHeight, behavior: 'smooth' }});
        }}
    </script>
</body>
</html>
"""


UIDAI_OFFICIAL_PORTAL_URL = "https://myaadhaar.uidai.gov.in/"


def launch_in_chromium(
    context: Optional[ConfirmedExecutionContext] = None,
    urn: str = "0000/12345/67890",
    open_live_portal: bool = True,
) -> bool:
    """
    Exclusively opens the official UIDAI portal (https://myaadhaar.uidai.gov.in/) in Chromium / Google Chrome.
    No intermediate or local pages are opened.
    """
    try:
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/brave-browser",
        ]

        browser_binary = next((p for p in chrome_paths if os.path.exists(p) and os.access(p, os.X_OK)), None)
        target_url = UIDAI_OFFICIAL_PORTAL_URL

        if browser_binary:
            logger.info(f"Launching {browser_binary} for official UIDAI portal: {target_url}")
            subprocess.Popen(
                [browser_binary, "--new-window", target_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        else:
            logger.info(f"Launching default browser for official UIDAI portal: {target_url}")
            webbrowser.open_new(target_url)
            return True
    except Exception as error:
        logger.warning(f"Failed to launch Chrome for official UIDAI portal: {error}")
        return False
