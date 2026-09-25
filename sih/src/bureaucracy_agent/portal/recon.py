"""Page-structure recon tool: inspects official portal page controls and dumps JSON map."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.bureaucracy_agent.portal.selectors import REGISTRATION_URLS

RECON_DUMP_PATH = Path("data/portal_recon_dump.json")


def run_portal_recon(target_url: Optional[str] = None, out_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Open visible browser at official registration URL, dump structure of controls to JSON.

    No CAPTCHA values or personal data are collected or written.
    """
    url = target_url or REGISTRATION_URLS[0]
    output_file = out_path or RECON_DUMP_PATH

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[RECON ERROR] Playwright is not installed. Run: pip install playwright && playwright install chromium")
        return {"error": "Playwright missing"}

    print(f"[RECON] Launching visible browser to inspect portal controls at: {url}")
    controls: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            # Handle RTI Guidelines page check & submit if present
            if "guidelines.php" in page.url:
                chk = page.query_selector("input[type='checkbox']")
                if chk:
                    chk.check()
                sub = page.query_selector("input[value='Submit']")
                if sub:
                    sub.click()
                page.wait_for_timeout(1500)

        except Exception as exc:  # noqa: BLE001
            print(f"[RECON WARNING] Navigation timeout or error: {exc}")

        title = page.title()
        final_url = page.url

        # Query input, select, textarea, img, button elements
        elements = page.query_selector_all("input, select, textarea, button, img, a[role='button']")
        for el in elements:
            try:
                tag_name = el.evaluate("e => e.tagName.toLowerCase()")
                el_type = el.get_attribute("type") or tag_name
                name = el.get_attribute("name") or ""
                el_id = el.get_attribute("id") or ""
                role = el.get_attribute("role") or ""
                placeholder = el.get_attribute("placeholder") or ""
                value = el.get_attribute("value") or ""
                src = el.get_attribute("src") or ""

                # Skip values of secret inputs
                if el_type in ("password", "hidden") or "captcha" in name.lower() or "captcha" in el_id.lower() or "captcha" in src.lower():
                    value = "[REDACTED_SECRET]"

                # Find associated label text if present
                label_text = ""
                if el_id:
                    lbl = page.query_selector(f"label[for='{el_id}']")
                    if lbl:
                        label_text = lbl.inner_text().strip()

                controls.append(
                    {
                        "tag": tag_name,
                        "type": el_type,
                        "id": el_id,
                        "name": name,
                        "role": role,
                        "placeholder": placeholder,
                        "label_text": label_text,
                        "src": src[:60] if src else "",
                        "sample_value": value[:20] if value else "",
                    }
                )
            except Exception:  # noqa: BLE001
                continue

        browser.close()

    dump_data = {
        "url": final_url,
        "title": title,
        "control_count": len(controls),
        "controls": controls,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(dump_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[RECON SUCCESS] Dumped {len(controls)} portal controls to {output_file}")
    return dump_data


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run_portal_recon(target)


if __name__ == "__main__":
    main()
