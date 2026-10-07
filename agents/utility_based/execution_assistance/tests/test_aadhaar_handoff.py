from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from agents.orchestration.document_input import AadhaarConfirmedData, ConfirmedField, FieldProvenance
from agents.utility_based.execution_assistance.interactive_session import InteractivePortalManager
from agents.utility_based.execution_assistance.schema import ConfirmedExecutionContext, ConfirmedFact, FactStatus


def _create_confirmed_data(aadhaar_num: str | None) -> AadhaarConfirmedData:
    confirmed_field = (
        ConfirmedField(
            value=aadhaar_num,
            source_document_id="doc-test-123",
            provenance=FieldProvenance.USER_CONFIRMED,
        )
        if aadhaar_num is not None
        else None
    )
    return AadhaarConfirmedData(
        aadhaar_number=confirmed_field,
        document_id="doc-test-123",
    )


def test_handoff_context_creation_synthetic_value_a():
    """TEST 1: Confirmed Aadhaar = synthetic value A -> context facts contains synthetic value A."""
    val_a = "111122223333"
    confirmed = _create_confirmed_data(val_a)
    ctx = confirmed.to_execution_context(session_id="session-a")

    assert "aadhaar_number" in ctx.facts
    assert ctx.facts["aadhaar_number"].value == val_a
    assert ctx.facts["aadhaar"].value == val_a
    assert ctx.facts["uid"].value == val_a


def test_handoff_context_creation_synthetic_value_b():
    """TEST 2: Confirmed Aadhaar = synthetic value B -> context facts contains synthetic value B."""
    val_b = "987654321098"
    confirmed = _create_confirmed_data(val_b)
    ctx = confirmed.to_execution_context(session_id="session-b")

    assert "aadhaar_number" in ctx.facts
    assert ctx.facts["aadhaar_number"].value == val_b
    assert ctx.facts["aadhaar"].value == val_b
    assert ctx.facts["uid"].value == val_b


def test_handoff_context_creation_missing_aadhaar():
    """TEST 3: Missing confirmed Aadhaar -> context facts does not contain aadhaar_number."""
    confirmed = _create_confirmed_data(None)
    ctx = confirmed.to_execution_context(session_id="session-missing")

    assert "aadhaar_number" not in ctx.facts
    assert "aadhaar" not in ctx.facts
    assert "uid" not in ctx.facts


def test_browser_autofill_receives_synthetic_value_a():
    """TEST 1 end-to-end: Browser autofill receives synthetic value A."""
    async def _run():
        val_a = "111122223333"
        confirmed = _create_confirmed_data(val_a)
        ctx = confirmed.to_execution_context(session_id="session-autofill-a")

        manager = InteractivePortalManager()
        session = MagicMock()
        session.context = ctx

        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.scroll_into_view_if_needed = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.press_sequentially = AsyncMock()

        loc_container = MagicMock()
        loc_container.first = mock_locator
        mock_page.locator = MagicMock(return_value=loc_container)
        mock_page.content = AsyncMock(return_value="<html>Login</html>")
        session.page = mock_page

        with patch.object(manager, "_smart_click_or_submit", new_callable=AsyncMock) as mock_click:
            mock_click.return_value = True
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw_instance = AsyncMock()
                mock_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)
                mock_browser = AsyncMock()
                mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_context = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.add_init_script = AsyncMock()
                mock_context.clear_cookies = AsyncMock()
                mock_context.pages = [mock_page]

                await manager._launch_and_navigate_login(session)

        # Verify press_sequentially was called with synthetic value A
        mock_locator.press_sequentially.assert_called_with("111122223333", delay=35)

    import asyncio
    asyncio.run(_run())


def test_browser_autofill_receives_synthetic_value_b():
    """TEST 2 end-to-end: Browser autofill receives synthetic value B."""
    async def _run():
        val_b = "987654321098"
        confirmed = _create_confirmed_data(val_b)
        ctx = confirmed.to_execution_context(session_id="session-autofill-b")

        manager = InteractivePortalManager()
        session = MagicMock()
        session.context = ctx

        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.scroll_into_view_if_needed = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.press_sequentially = AsyncMock()

        loc_container = MagicMock()
        loc_container.first = mock_locator
        mock_page.locator = MagicMock(return_value=loc_container)
        mock_page.content = AsyncMock(return_value="<html>Login</html>")
        session.page = mock_page

        with patch.object(manager, "_smart_click_or_submit", new_callable=AsyncMock) as mock_click:
            mock_click.return_value = True
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw_instance = AsyncMock()
                mock_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)
                mock_browser = AsyncMock()
                mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_context = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.add_init_script = AsyncMock()
                mock_context.clear_cookies = AsyncMock()
                mock_context.pages = [mock_page]

                await manager._launch_and_navigate_login(session)

        # Verify press_sequentially was called with synthetic value B
        mock_locator.press_sequentially.assert_called_with("987654321098", delay=35)

    import asyncio
    asyncio.run(_run())


def test_browser_autofill_skips_when_aadhaar_missing():
    """TEST 3 end-to-end: Missing confirmed Aadhaar -> browser autofill is NOT called with any fallback."""
    async def _run():
        confirmed = _create_confirmed_data(None)
        ctx = confirmed.to_execution_context(session_id="session-autofill-missing")

        manager = InteractivePortalManager()
        session = MagicMock()
        session.context = ctx

        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.scroll_into_view_if_needed = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.press_sequentially = AsyncMock()

        loc_container = MagicMock()
        loc_container.first = mock_locator
        mock_page.locator = MagicMock(return_value=loc_container)
        mock_page.content = AsyncMock(return_value="<html>Login</html>")
        session.page = mock_page

        with patch.object(manager, "_smart_click_or_submit", new_callable=AsyncMock) as mock_click:
            mock_click.return_value = True
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw_instance = AsyncMock()
                mock_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)
                mock_browser = AsyncMock()
                mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_context = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.add_init_script = AsyncMock()
                mock_context.clear_cookies = AsyncMock()
                mock_context.pages = [mock_page]

                await manager._launch_and_navigate_login(session)

        # Verify press_sequentially was NEVER called (no fallback value used)
        mock_locator.press_sequentially.assert_not_called()

    import asyncio
    asyncio.run(_run())


def test_navigation_sequence_restored():
    """Verify: browser initialization -> MyAadhaar origin -> direct Resident Login -> UID field check."""
    async def _run():
        confirmed = _create_confirmed_data("123456789012")
        ctx = confirmed.to_execution_context(session_id="session-nav-test")

        manager = InteractivePortalManager()
        session = MagicMock()
        session.context = ctx

        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_locator.scroll_into_view_if_needed = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_locator.press_sequentially = AsyncMock()

        loc_container = MagicMock()
        loc_container.first = mock_locator
        mock_page.locator = MagicMock(return_value=loc_container)
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()

        session.page = mock_page

        with patch.object(manager, "_smart_click_or_submit", new_callable=AsyncMock) as mock_click:
            mock_click.return_value = True
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw_instance = AsyncMock()
                mock_pw.return_value.start = AsyncMock(return_value=mock_pw_instance)
                mock_browser = AsyncMock()
                mock_pw_instance.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_context = AsyncMock()
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_context.add_init_script = AsyncMock()
                mock_context.clear_cookies = AsyncMock()
                mock_context.pages = [mock_page]

                await manager._launch_and_navigate_login(session)

        # Verify navigation sequence:
        # 1. origin_url: https://myaadhaar.uidai.gov.in/
        # 2. login_url: https://myaadhaar.uidai.gov.in/login
        goto_calls = mock_page.goto.call_args_list
        assert len(goto_calls) >= 2
        assert goto_calls[0] == call("https://myaadhaar.uidai.gov.in/", wait_until="domcontentloaded", timeout=30000)
        assert goto_calls[1] == call("https://myaadhaar.uidai.gov.in/login", wait_until="domcontentloaded", timeout=30000)

        # Verify UID field DOM readiness check was called
        mock_page.wait_for_selector.assert_called_once()

    import asyncio
    asyncio.run(_run())
