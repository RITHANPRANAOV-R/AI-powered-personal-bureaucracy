"""Diagnostic privacy/access tests: no live browser, server, database or event loop."""
import ast
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from agents.utility_based.execution_assistance.portal_inspection import STRUCTURE_SCRIPT, require_local_inspection, inspect_existing_session
from agents.utility_based.execution_assistance.tests.test_demo_recovery import immediate
from agents.utility_based.execution_assistance.interactive_session import PortalStage


def request(host="127.0.0.1", origin="http://localhost:5173", authority="127.0.0.1:8000", extra=None):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={"host":authority,"origin":origin,**(extra or {})})


@pytest.mark.parametrize("deadline,now", [(None,0),(5,5),(5,6)])
def test_disabled_and_expired_inspection_fail_closed(deadline, now):
    with pytest.raises(HTTPException) as error: require_local_inspection(request(),deadline,now)
    assert error.value.status_code == 404
    assert error.value.detail["code"] == ("PORTAL_DIAGNOSTIC_DISABLED" if deadline is None else "PORTAL_DIAGNOSTIC_EXPIRED")


@pytest.mark.parametrize("req", [request(host="192.0.2.1"),request(origin="https://unrelated.example"),
    request(authority="unrelated.example:8000"),request(extra={"x-forwarded-for":"127.0.0.1"}),request(origin=None)])
def test_nonlocal_origin_and_proxy_requests_rejected(req):
    with pytest.raises(HTTPException) as error: require_local_inspection(req,10,0)
    assert error.value.status_code == 403


def test_direct_loopback_and_exact_origin_allowed():
    require_local_inspection(request(),10,0)


def test_renderer_never_reads_values_cookies_query_or_document_body():
    runner = r"""
const fs = require('fs');
const script = fs.readFileSync(0,'utf8');
const forbid = () => {throw Error('Forbidden private property access');};
const control = {tagName:'INPUT',disabled:false,getClientRects:()=>[{}],labels:[{textContent:'House number'}],
 getAttribute:n=>({id:'mat-input-6',name:'houseNumber',formcontrolname:'houseNumber','aria-label':'Private Citizen',placeholder:'House number'}[n]||null)};
for (const key of ['value','files','innerHTML','outerHTML']) Object.defineProperty(control,key,{get:forbid});
global.getComputedStyle=()=>({display:'block',visibility:'visible'});
global.location={origin:'https://myaadhaar.uidai.gov.in',pathname:'/ssup/address/123456789012'};
for(const key of ['search','href']) Object.defineProperty(location,key,{get:forbid});
global.document={title:'myAadhaar',readyState:'complete',querySelectorAll:q=>q.startsWith('input')?[control]:q.startsWith('h1')?[{tagName:'H1',textContent:'Private Citizen',getClientRects:()=>[{}]}]:[]};
for(const key of ['body','cookie']) Object.defineProperty(document,key,{get:forbid});
const result = eval('('+script+')')();
const serialized=JSON.stringify(result);
if(serialized.includes('Private Citizen')||serialized.includes('123456789012')) throw Error('Private metadata escaped filtering');
if(result.controls[0].name!=='houseNumber'||result.controls[0].aria_label!=='[redacted]'||result.path!=='/ssup/address/[redacted]') throw Error('Unexpected sanitized structure');
location.pathname='/ssup/demoUpdate/update/en_IN';
document.querySelectorAll=q=>q.startsWith('input')?[control]:q.startsWith('h1')?['Current Details','Details to be Updated'].map(textContent=>({tagName:'H2',textContent,getClientRects:()=>[{}]})):[];
const documented=eval('('+script+')')();
if(documented.path!=='/ssup/demoUpdate/update/en_IN'||JSON.stringify(documented.headings.map(h=>h.label))!==JSON.stringify(['Current Details','Details to be Updated'])) throw Error('Documented safe route/labels were lost');
process.stdout.write('PRIVACY_OK');
"""
    result = subprocess.run(["node","-e",runner],input=STRUCTURE_SCRIPT,text=True,capture_output=True,timeout=10)
    assert result.returncode == 0, "Structural privacy check failed"
    assert result.stdout == "PRIVACY_OK"


@pytest.mark.parametrize("change", [None,"version","active","page"])
def test_capture_preserves_uncertainty_and_discards_changed_session(monkeypatch,change):
    async def without_loop(coro, timeout):
        assert timeout == 10
        return await coro
    monkeypatch.setattr('agents.utility_based.execution_assistance.portal_inspection.asyncio.wait_for',without_loop)
    page=SimpleNamespace(context=object())
    session=SimpleNamespace(page=page,browser=object(),current_stage=PortalStage.STAGE_2_SERVICE,
                            execution_version=7,active_attempt=None,execution_uncertain=True)
    async def evaluate(script):
        assert script == STRUCTURE_SCRIPT
        if change == "version": session.execution_version+=1
        if change == "active": session.active_attempt='new'
        if change == "page": session.page=SimpleNamespace(context=object())
        return {"origin":"https://myaadhaar.uidai.gov.in","path":"/ssup/address","controls":[]}
    page.frames=[SimpleNamespace(evaluate=evaluate)]
    manager=SimpleNamespace(_attempt_lock=threading.RLock(),_sessions={"synthetic":session},_check_authentication_continuity=lambda _:None)
    if change:
        with pytest.raises(HTTPException) as error: immediate(inspect_existing_session(manager,'synthetic'))
        assert error.value.status_code == 409
    else:
        result=immediate(inspect_existing_session(manager,'synthetic'))
        assert result['state_version']==7 and result['stage']=='stage_2_service'
        assert result['page_reference'] == session._page_observation_reference
        assert result['last_result_binding'] == {}
    assert session.execution_uncertain is True


def test_api_route_authorizes_capability_before_inspecting_without_importing_runtime():
    # AST evidence avoids production app import (which constructs the Chroma-backed runtime).
    source=Path('api/app.py').read_text(encoding='utf-8')
    tree=ast.parse(source)
    factory=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_app')
    route=next(n for n in factory.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='inspect_browser_structure')
    calls=[n.func.id for n in ast.walk(route) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert calls.index('require_local_inspection') < calls.index('authorize_session') < calls.index('inspect_existing_session')
    assert '"Cache-Control": "no-store"' in ast.get_source_segment(source,route)
    assert 'AADHAAR_ENABLE_PORTAL_DIAGNOSTICS' in source and '900' in source


@pytest.mark.parametrize("authorized", [False, True])
def test_actual_diagnostic_route_requires_capability_before_snapshot(monkeypatch, authorized):
    # Execute only the actual route, without importing api.app's production startup runtime.
    tree=ast.parse(Path('api/app.py').read_text(encoding='utf-8'))
    factory=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_app')
    route=next(n for n in factory.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='inspect_browser_structure')
    route.decorator_list=[]
    calls=[]
    def authorize(session_id, req):
        calls.append('authorize')
        if req.headers.get('authorization') != 'Bearer synthetic':
            raise HTTPException(status_code=403,detail='Capability rejected')
    async def capture(manager, session_id):
        calls.append('capture')
        return {'schema':'sanitized-portal-structure-v1','frames':[]}
    monkeypatch.setattr('agents.utility_based.execution_assistance.portal_inspection.inspect_existing_session',capture)
    scope={'Request':object,'HTTPException':HTTPException,'inspection_deadline':10,
           'time':SimpleNamespace(monotonic=lambda:0),'authorize_session':authorize}
    exec(compile(ast.Module(body=[route],type_ignores=[]),'api/app.py','exec'),scope)
    req=request(extra={'authorization':'Bearer synthetic'} if authorized else {})
    coroutine=scope['inspect_browser_structure']({'session_id':'synthetic'},req)
    if authorized:
        response=immediate(coroutine)
        assert calls == ['authorize','capture','authorize']
        assert response.headers['cache-control']=='no-store'
    else:
        with pytest.raises(HTTPException) as error: immediate(coroutine)
        assert error.value.status_code==403 and calls==['authorize']


def test_capture_binds_to_exact_last_result_page_attempt_and_version(monkeypatch):
    from agents.utility_based.execution_assistance.tests.test_stage_verification import address
    from agents.utility_based.execution_assistance.tests.test_demo_recovery import request as execute
    manager, session, page, controls = address()
    controls["house"].append(controls["house"][-1])
    response = immediate(execute(manager, session))
    assert response["execution_result"]["status"] == "UNKNOWN"
    async def without_loop(coro, timeout):
        return await coro
    monkeypatch.setattr('agents.utility_based.execution_assistance.portal_inspection.asyncio.wait_for',without_loop)
    page.frames=[SimpleNamespace(evaluate=AsyncMock(return_value={"origin":"https://myaadhaar.uidai.gov.in","path":"/ssup/demoUpdate/update/en_IN","controls":[]}))]
    snapshot=immediate(inspect_existing_session(manager,session.session_id))
    assert snapshot["last_result_binding"] == response["execution_diagnostic"]
    assert snapshot["page_reference"] == response["execution_diagnostic"]["page_reference"]
    assert snapshot["state_version"] == response["execution_state_version"]
    page.evaluate.assert_not_awaited()
    manager._smart_fill.assert_not_awaited()
