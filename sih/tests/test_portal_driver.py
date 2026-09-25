"""Unit tests for portal driver, extraction, and allowlist checks."""

import unittest

from agents.execution_assistance.safety import check_host_allowlist
from src.bureaucracy_agent.portal.extract import extract_confirmation_details


class TestPortalDriver(unittest.TestCase):
    def test_host_allowlist_checking(self):
        allowed = ["rtionline.gov.in", "www.rtionline.gov.in"]

        self.assertTrue(check_host_allowlist("https://rtionline.gov.in/guidelines.php?request", allowed))
        self.assertTrue(check_host_allowlist("https://www.rtionline.gov.in/request/request.php", allowed))
        self.assertFalse(check_host_allowlist("https://malicious-phishing.com/rti", allowed))

    def test_extract_confirmation_details_with_registration_number(self):
        page_text = """
        RTI Online Portal
        Your Request has been Submitted Successfully.
        Registration Number: MOWR/R/2026/60123
        Date & Time: 25/09/2026 10:30 AM
        Public Authority: Ministry of Home Affairs
        Status: Submitted Successfully
        """
        observed, ref_str, details = extract_confirmation_details(page_text)
        self.assertTrue(observed)
        self.assertIn("MOWR/R/2026/60123", ref_str)
        self.assertIn("Registration Number", details)

    def test_extract_confirmation_details_without_reference(self):
        page_text = "Welcome to RTI Online Portal. Please select your service from the menu."
        observed, ref_str, details = extract_confirmation_details(page_text)
        self.assertFalse(observed)
        self.assertIsNone(ref_str)
        self.assertEqual(len(details), 0)


if __name__ == "__main__":
    unittest.main()
