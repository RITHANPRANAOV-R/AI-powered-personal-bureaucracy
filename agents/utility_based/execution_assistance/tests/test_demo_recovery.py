"""Immediate deterministic mocks: no event-loop, browser, HTTP or government action."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from agents.orchestration.document_input.tests.test_canonical_contracts import extract
from agents.utility_based.execution_assistance.tests.test_authentication_session import fixture_session
from agents.utility_based.execution_assistance.interactive_session import PortalStage, UIDAI_LOGIN_URL
from agents.utility_based.execution_assistance.schema import ActionExecutionResult, ExecutionOutcome, ConfirmedExecutionContext


def immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coroutine.close()
    raise AssertionError('Mock unexpectedly suspended; no runtime policy workaround is used.')


@pytest.mark.parametrize('pin', ['641018', '641025'])
def test_old_and_proposed_pin_are_distinct_and_preserved_through_mapping(pin):
    proposed=f'no.456, race course, coimbatore-{pin}'
    service, result=extract('638106', {'new_address': proposed, 'pincode': pin})
    assert not result.conflicts
    original=result.data.existing_address.value
    assert '638106' in original
    context=service.confirm(result).to_execution_context('synthetic')
    reconstructed=ConfirmedExecutionContext.model_validate(context.model_dump(mode='json'))
    manager, _, _=fixture_session()
    fields=manager._parse_address_components({k:v.value for k,v in reconstructed.facts.items()})
    assert reconstructed.facts['existing_address'].value == original
    assert fields['new_address'] == proposed and fields['pincode'] == pin


@pytest.mark.parametrize('pin',['641018','641025'])
def test_canonical_pin_reaches_existing_pin_fill_helper_unchanged(pin):
    service,result=extract('638106',{'new_address':f'New street {pin}','pincode':pin})
    manager,session,page=fixture_session()
    session.context=service.confirm(result).to_execution_context(session.session_id)
    page.evaluate=AsyncMock()
    manager._smart_fill=AsyncMock()
    manager._select_dropdown_option=AsyncMock(return_value={})
    manager._validate_address_stage=AsyncMock(return_value={'pin_valid':False})
    # Isolate canonical PIN transport after the newly explicit readiness prerequisite.
    manager._verify_address_form_ready=AsyncMock(return_value=ActionExecutionResult(
        status=ExecutionOutcome.VERIFIED_SUCCESS, message='Fixture form ready', verification_evidence='Fixture readiness'))
    immediate(manager._execute_stage_action_on_portal(session,PortalStage.STAGE_3_ADDRESS))
    calls=[c for c in manager._smart_fill.await_args_list if 'input[name*="pincode" i]' in c.args[1]]
    assert len(calls)==1 and calls[0].args[2]==pin
    manager._smart_click_or_submit.assert_not_awaited()


@pytest.mark.parametrize('proposed,explicit', [('New street 641018 or 641025','641018'), ('New street 641018','641025')])
def test_ambiguity_within_new_address_is_not_overridden(proposed,explicit):
    service,result=extract('638106',{'new_address':proposed,'pincode':explicit})
    assert result.data.pincode is None and 'pincode' in result.conflicts
    with pytest.raises(ValueError,match='Explicit correction'): service.confirm(result)


def test_new_address_without_pin_does_not_borrow_old_pin():
    _,result=extract('638106',{'new_address':'A new street without a PIN'})
    assert result.data.pincode is None


@pytest.mark.parametrize('proposed', ['New street 641018 or 641025', 'New street 641025'])
def test_review_correction_cannot_bypass_proposed_pin_consistency(proposed):
    service,result=extract('638106')
    with pytest.raises(ValueError,match='proposed new address'):
        service.confirm(result,{'new_address':proposed,'pincode':'641018'})


def otp_session(visible=False):
    manager,session,page=fixture_session()
    session.current_stage=PortalStage.STAGE_1A_OTP
    page.url=UIDAI_LOGIN_URL
    page.otp_visible=visible
    locator=SimpleNamespace(is_visible=AsyncMock(side_effect=lambda **kw:page.otp_visible),
        is_enabled=AsyncMock(return_value=True),
        count=AsyncMock(return_value=1),focus=AsyncMock())
    page.locator=lambda selector:SimpleNamespace(first=locator)
    return manager,session,page


def request(manager,session,identity='attempt',stage=None,version=None):
    return manager.submit_step(session.session_id,True,request_id=identity,
        expected_stage=stage or session.current_stage.value,
        expected_state_version=session.execution_version if version is None else version)


def test_send_otp_runs_existing_handler_and_verified_transition_advances_once():
    manager,session,page=otp_session()
    manager._smart_click_or_submit=AsyncMock(side_effect=lambda *a,**kw:setattr(page,'otp_visible',True))
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='VERIFIED_SUCCESS'
    assert response['execution_result']['verification_evidence']
    assert session.current_stage==PortalStage.STAGE_1B_LOGIN
    manager._smart_click_or_submit.assert_awaited_once()
    assert immediate(request(manager,session,'attempt',PortalStage.STAGE_1A_OTP.value,0))['execution_result']['status']=='BLOCKED'
    assert manager._smart_click_or_submit.await_count==1


@pytest.mark.parametrize('throws',[False,True])
def test_unobserved_or_exception_outcome_is_uncertain_and_no_retry(throws):
    manager,session,page=otp_session()
    manager._smart_click_or_submit=AsyncMock(side_effect=RuntimeError('synthetic') if throws else None)
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='UNKNOWN'
    assert 'Inspect the existing UIDAI window' in response['message']
    assert response['execution_uncertain'] and not response['retry_permitted']
    assert session.current_stage==PortalStage.STAGE_1A_OTP
    assert immediate(request(manager,session,'fresh'))['execution_result']['status']=='BLOCKED'
    assert manager._smart_click_or_submit.await_count==1


def test_authoritatively_reported_failure_remains_failure_without_safe_retry():
    manager,session,_=otp_session()
    manager._execute_stage_action_on_portal=AsyncMock(return_value=ActionExecutionResult(
        status=ExecutionOutcome.FAILED,message='Synthetic observed rejection',verification_evidence='Synthetic authoritative portal rejection'))
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='FAILED'
    assert response['execution_uncertain'] and not response['retry_permitted']
    assert immediate(request(manager,session,'fresh'))['execution_result']['status']=='BLOCKED'


def test_existing_checkpoint_is_not_a_new_otp_send():
    manager,session,_=otp_session(True)
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='NEEDS_USER'
    assert response['retry_permitted'] and not response['execution_uncertain']
    manager._smart_click_or_submit.assert_not_awaited()


def test_disabled_otp_checkpoint_cannot_claim_ready_success():
    manager,session,page=otp_session()
    page.locator('otp').first.is_enabled.return_value=False
    manager._smart_click_or_submit=AsyncMock(side_effect=lambda *a,**kw:setattr(page,'otp_visible',True))
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='UNKNOWN'
    assert response['execution_uncertain']


def test_concurrent_request_blocked_while_dispatch_is_reserved():
    manager,session,_=otp_session()
    class Pause:
        def __await__(self):
            yield 'paused'
    async def action(*args):
        assert not manager._attempt_lock._is_owned()
        await Pause()
        return ActionExecutionResult(status=ExecutionOutcome.UNKNOWN,message='Synthetic uncertain dispatch')
    manager._execute_stage_action_on_portal=action
    first=request(manager,session)
    assert first.send(None)=='paused'
    try:
        assert immediate(request(manager,session,'concurrent'))['execution_result']['status']=='BLOCKED'
        with pytest.raises(StopIteration) as done:first.send(None)
        assert done.value.value['execution_uncertain']
    finally:first.close()


def test_changed_origin_after_action_cannot_verify_success():
    manager,session,page=otp_session()
    def change(*a,**kw):
        page.otp_visible=True
        page.url='https://unrelated.example/'
    manager._smart_click_or_submit=AsyncMock(side_effect=change)
    assert immediate(request(manager,session))['execution_result']['status']=='UNKNOWN'


def test_origin_change_during_initial_inspection_blocks_dispatch():
    manager,session,page=otp_session()
    async def visible(**kwargs):
        page.url='https://unrelated.example/'
        return False
    page.locator=lambda selector:SimpleNamespace(first=SimpleNamespace(is_visible=visible))
    response=immediate(request(manager,session))
    assert response['execution_result']['status']=='NEEDS_USER'
    assert response['retry_permitted'] and not response['execution_uncertain']
    manager._smart_click_or_submit.assert_not_awaited()
