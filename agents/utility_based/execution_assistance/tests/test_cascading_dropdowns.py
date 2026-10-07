from __future__ import annotations

import pytest
import anyio
from unittest.mock import AsyncMock, MagicMock

from agents.utility_based.execution_assistance.interactive_session import (
    InteractivePortalManager,
)


def _make_mock_page(options):
    mock_loc = MagicMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.get_attribute = AsyncMock(return_value="")
    mock_loc.select_option = AsyncMock()
    mock_loc.dispatch_event = AsyncMock()

    def mock_eval(expr, *args):
        if "tagName" in str(expr):
            return "select"
        return options

    mock_loc.evaluate = AsyncMock(side_effect=mock_eval)

    mock_loc_obj = MagicMock()
    mock_loc_obj.first = mock_loc

    mock_page = MagicMock()
    mock_page.locator.return_value = mock_loc_obj
    mock_page.wait_for_selector = AsyncMock()
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()
    return mock_page, mock_loc


@pytest.mark.anyio
async def test_parse_address_components_cascading_fields():
    manager = InteractivePortalManager()
    facts = {
        "new_address": "Flat 402, Lotus Apts, 12th Main Road, Koramangala 4th Block, Bengaluru, 560034",
        "pincode": "560034",
        "vtc": "Bengaluru",
        "post_office": "Koramangala I.E. S.O",
    }
    addr_data = manager._parse_address_components(facts)
    assert addr_data["pincode"] == "560034"
    assert addr_data["vtc"] == "Bengaluru"
    assert addr_data["post_office"] == "Koramangala I.E. S.O"


@pytest.mark.anyio
async def test_select_dropdown_option_single_match():
    manager = InteractivePortalManager()
    options = [
        {"value": "", "text": "Select Village/Town/City", "disabled": False},
        {"value": "101", "text": "Bengaluru", "disabled": False},
        {"value": "102", "text": "Mysuru", "disabled": False},
    ]
    mock_page, mock_loc = _make_mock_page(options)

    res = await manager._select_dropdown_option(
        mock_page,
        ['select[name="vtc"]'],
        "bengaluru",
        "Village/Town/City",
    )
    assert res["status"] == "selected"
    assert res["value"] == "Bengaluru"
    mock_loc.select_option.assert_called_once_with(value="101")


@pytest.mark.anyio
async def test_select_dropdown_option_multiple_matches():
    manager = InteractivePortalManager()
    options = [
        {"value": "101", "text": "Koramangala", "disabled": False},
        {"value": "102", "text": "Koramangala", "disabled": False},
    ]
    mock_page, mock_loc = _make_mock_page(options)

    res = await manager._select_dropdown_option(
        mock_page,
        ['select[name="postOffice"]'],
        "Koramangala",
        "Post Office",
    )
    assert res["status"] == "multiple_matches"
    assert len(res["options"]) == 2
    assert not mock_loc.select_option.called


@pytest.mark.anyio
async def test_select_dropdown_option_no_match():
    manager = InteractivePortalManager()
    options = [
        {"value": "101", "text": "Indiranagar S.O", "disabled": False},
    ]
    mock_page, mock_loc = _make_mock_page(options)

    res = await manager._select_dropdown_option(
        mock_page,
        ['select[name="postOffice"]'],
        "Koramangala S.O",
        "Post Office",
    )
    assert res["status"] == "no_match"
    assert "Indiranagar S.O" in res["available_options"]
    assert not mock_loc.select_option.called


@pytest.mark.anyio
async def test_select_dropdown_option_missing_value():
    manager = InteractivePortalManager()
    mock_page = AsyncMock()

    res = await manager._select_dropdown_option(
        mock_page,
        ['select[name="postOffice"]'],
        "",
        "Post Office",
    )
    assert res["status"] == "missing_value"


@pytest.mark.anyio
async def test_select_dropdown_option_mat_select_cdk_overlay():
    manager = InteractivePortalManager()

    mock_loc = MagicMock()
    mock_loc.click = AsyncMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.evaluate = AsyncMock(return_value="mat-select")
    mock_loc.get_attribute = AsyncMock(return_value="combobox")
    mock_loc.inner_text = AsyncMock(return_value="Coimbatore Central")

    mock_opt1 = MagicMock()
    mock_opt1.inner_text = AsyncMock(return_value="Coimbatore North S.O")

    mock_opt2 = MagicMock()
    mock_opt2.inner_text = AsyncMock(return_value="Coimbatore Central")
    mock_opt2.click = AsyncMock()

    mock_options_locator = MagicMock()
    mock_options_locator.count = AsyncMock(return_value=2)
    mock_options_locator.nth.side_effect = lambda idx: mock_opt1 if idx == 0 else mock_opt2

    mock_page = MagicMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    def locator_side_effect(selector):
        if "cdk-overlay" in selector or "mat-option" in selector:
            return mock_options_locator
        obj = MagicMock()
        obj.first = mock_loc
        return obj

    mock_page.locator.side_effect = locator_side_effect

    res = await manager._select_dropdown_option(
        mock_page,
        ['mat-select[formcontrolname="postOffice"]'],
        "Coimbatore Central",
        "Post Office",
    )

    mock_page.wait_for_selector.assert_called_once()
    assert "cdk-overlay" in mock_page.wait_for_selector.call_args[0][0]
    assert res["status"] == "selected"
    assert res["value"] == "Coimbatore Central"
    mock_opt2.click.assert_called_once()


@pytest.mark.anyio
async def test_select_dropdown_option_mat_select_no_first_option_fallback():
    manager = InteractivePortalManager()

    mock_loc = MagicMock()
    mock_loc.click = AsyncMock()
    mock_loc.count = AsyncMock(return_value=1)
    mock_loc.evaluate = AsyncMock(return_value="mat-select")
    mock_loc.get_attribute = AsyncMock(return_value="combobox")

    mock_opt1 = MagicMock()
    mock_opt1.inner_text = AsyncMock(return_value="Coimbatore North S.O")
    mock_opt1.click = AsyncMock()

    mock_options_locator = MagicMock()
    mock_options_locator.count = AsyncMock(return_value=1)
    mock_options_locator.nth.return_value = mock_opt1

    mock_page = MagicMock()
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.keyboard = MagicMock()
    mock_page.keyboard.press = AsyncMock()

    def locator_side_effect(selector):
        if "cdk-overlay" in selector or "mat-option" in selector:
            return mock_options_locator
        obj = MagicMock()
        obj.first = mock_loc
        return obj

    mock_page.locator.side_effect = locator_side_effect

    res = await manager._select_dropdown_option(
        mock_page,
        ['mat-select[formcontrolname="postOffice"]'],
        "Coimbatore Central",
        "Post Office",
    )

    assert res["status"] == "no_match"
    mock_opt1.click.assert_not_called()
    mock_page.keyboard.press.assert_called_with("Escape")


@pytest.mark.anyio
async def test_validate_address_stage_incomplete():
    manager = InteractivePortalManager()
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = {
        "pin_valid": True,
        "vtc_selected": True,
        "po_selected": False,
        "vtc_val": "Coimbatore South",
        "po_val": "",
    }

    res = await manager._validate_address_stage(mock_page)
    assert res["pin_valid"] is True
    assert res["vtc_selected"] is True
    assert res["po_selected"] is False
