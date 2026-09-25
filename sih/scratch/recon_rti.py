"""RTI Online Recon Script for request_email_check.php and request.php.
"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def run_recon():
    output_path = Path("/Users/haripraks/sih3/sih/scratch/rti_recon.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    recon_data = {
        "email_check_page": {},
        "email_check_controls": [],
        "request_form_page": {},
        "request_form_controls": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        print("[RECON] Navigating to https://rtionline.gov.in/guidelines.php?request ...")
        page.goto("https://rtionline.gov.in/guidelines.php?request", timeout=30000)
        page.wait_for_timeout(1500)

        if page.is_visible("input[name='CHECKBOX_1']"):
            page.check("input[name='CHECKBOX_1']")

        if page.is_visible("input[value='Submit']"):
            page.click("input[value='Submit']")
            page.wait_for_timeout(2000)

        recon_data["email_check_page"] = {"url": page.url, "title": page.title()}

        for el in page.query_selector_all("input, textarea, select, img"):
            try:
                recon_data["email_check_controls"].append({
                    "tag": el.evaluate("e => e.tagName.toLowerCase()"),
                    "id": el.get_attribute("id") or "",
                    "name": el.get_attribute("name") or "",
                    "type": el.get_attribute("type") or "",
                    "value": (el.get_attribute("value") or "")[:30],
                    "src": el.get_attribute("src") or "",
                })
            except Exception:
                pass

        # Also inspect direct request.php page if reachable
        print("[RECON] Navigating to https://rtionline.gov.in/request/request.php ...")
        page.goto("https://rtionline.gov.in/request/request.php", timeout=30000)
        page.wait_for_timeout(2000)

        recon_data["request_form_page"] = {"url": page.url, "title": page.title()}

        for el in page.query_selector_all("input, textarea, select, img"):
            try:
                recon_data["request_form_controls"].append({
                    "tag": el.evaluate("e => e.tagName.toLowerCase()"),
                    "id": el.get_attribute("id") or "",
                    "name": el.get_attribute("name") or "",
                    "type": el.get_attribute("type") or "",
                    "value": (el.get_attribute("value") or "")[:30],
                    "src": el.get_attribute("src") or "",
                })
            except Exception:
                pass

        output_path.write_text(json.dumps(recon_data, indent=2))
        print(f"[RECON] Wrote detailed recon to {output_path}")
        browser.close()

if __name__ == "__main__":
    run_recon()
