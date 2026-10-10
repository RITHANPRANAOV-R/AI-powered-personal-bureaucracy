import test from 'node:test';
import assert from 'node:assert/strict';
import { interpretExecutionStep } from './executionStepState.js';

const stage = 'stage_1b_login';
const verified = () => ({
    completed_stage: stage, current_stage: 'stage_2_service',
    stage_info: { id: 'stage_2_service' }, is_completed: false,
    execution_result: { status: 'VERIFIED_SUCCESS', message: 'Observed', verification_evidence: 'Fixture authenticated state' },
});

test('verified external state permits stage completion', () => {
    assert.equal(interpretExecutionStep(verified(), stage).completed, true);
});
for (const status of ['FAILED', 'NEEDS_USER', 'BLOCKED', 'UNKNOWN']) {
    test(`HTTP 200 with ${status} cannot complete a stage`, () => {
        const response = { ...verified(), status: 'success', is_completed: true };
        response.execution_result.status = status;
        assert.equal(interpretExecutionStep(response, stage).completed, false);
    });
}
for (const execution_result of [undefined, null, {}, { status: 'success' }, { status: 'VERIFIED_SUCCESS' }]) {
    test(`missing/malformed result fails closed: ${JSON.stringify(execution_result)}`, () => {
        assert.equal(interpretExecutionStep({ ...verified(), execution_result }, stage).completed, false);
    });
}
test('stale or inconsistent stage response cannot complete', () => {
    assert.equal(interpretExecutionStep(verified(), 'stage_3_address').completed, false);
    const response = verified();
    response.current_stage = stage;
    assert.equal(interpretExecutionStep(response, stage).completed, false);
});
test('final completion requires official reference with verified evidence', () => {
    const response = { ...verified(), completed_stage: 'stage_5_review', current_stage: 'stage_6_completed', is_completed: true, urn: 'local-URN' };
    assert.equal(interpretExecutionStep(response, 'stage_5_review').final, false);
    response.execution_result.official_reference = 'official-fixture';
    response.urn = 'official-fixture';
    assert.equal(interpretExecutionStep(response, 'stage_5_review').final, true);
});

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
const require = createRequire(import.meta.url);
const { transformSync } = require('esbuild');
// Expose the real handler in memory only; the component source is not changed.
const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8')
    .replace('    const isBusy =', '    globalThis.fixtureSubmit = handleAppSubmitStep; globalThis.fixtureInvalidate = () => { executionOperation.current += 1; };\n    const isBusy =');
const compiled = transformSync(source, { loader: 'jsx', format: 'cjs' }).code;
async function submitThroughComponent(response, supersede = false, submittedStage = stage, inputs = undefined) {
    const updates = new Map();
    let index = 0;
    const initial = new Map([[0, 3], [13, true], [14, { id: submittedStage, title: 'Fixture checkpoint', step_number: 2 }], [10, 'UNKNOWN: old My transaction history error']]);
    if (inputs) initial.set(21, inputs);
    const React = {
        useRef() { return { current: 0 }; },
        useState(defaultValue) {
            const key = index++;
            return [initial.has(key) ? initial.get(key) : defaultValue, (value) => updates.set(key, value)];
        },
        createElement() { return null; },
    };
    const context = vm.createContext({
        React, module: { exports: {} },
        require(name) {
            if (name === 'react') return React;
            if (name === 'lucide-react') return {};
            if (name === './executionStepState') return { interpretExecutionStep };
            if (name === './documentApi') return { submitBrowserStep: async (...args) => {
                updates.set('submittedInputs', args[3]);
                await Promise.resolve();
                if (supersede) context.fixtureInvalidate();
                return response;
            } };
            throw new Error(`Unexpected import: ${name}`);
        },
    });
    vm.runInContext(compiled, context);
    context.module.exports.default();
    await context.fixtureSubmit();
    return updates;
}
for (const status of ['FAILED', 'NEEDS_USER', 'BLOCKED', 'UNKNOWN']) {
    test(`component keeps stage pending for HTTP 200 / ${status}`, async () => {
        const response = verified();
        response.execution_result.status = status;
        const updates = await submitThroughComponent(response);
        assert.equal(updates.has(15), false);
        assert.equal(updates.has(17), false);
        assert.equal(updates.has(14), false);
        assert.match(updates.get(10), new RegExp(status));
    });
}
test('component fails closed on missing execution result', async () => {
    const updates = await submitThroughComponent({ is_completed: true, status: 'success' });
    assert.equal(updates.has(15), false);
    assert.equal(updates.has(17), false);
});
test('component records only verified stage completion', async () => {
    const updates = await submitThroughComponent(verified());
    assert.equal(updates.has(15), true);
    assert.equal(updates.get(14).id, 'stage_2_service');
    assert.equal(updates.has(17), false);
});

test('verified flag with an incomplete contract cannot complete', () => {
    const response = verified();
    delete response.execution_result.message;
    assert.equal(interpretExecutionStep(response, stage).completed, false);
});


test('new confirmed result clears obsolete history error and advances OTP stage', async () => {
    const updates = await submitThroughComponent(verified());
    assert.equal(updates.get(10), '');
    assert.equal(updates.get(14).id, 'stage_2_service');
});

for (const status of ['UNKNOWN', 'VERIFIED_SUCCESS']) {
    test(`superseded ${status} response cannot overwrite newer execution operation`, async () => {
        const response = verified();
        response.execution_result.status = status;
        response.execution_result.message = 'old My transaction history failure';
        const updates = await submitThroughComponent(response, true);
        assert.equal(updates.get(10), '');
        assert.equal(updates.has(14), false);
        assert.equal(updates.has(15), false);
        assert.equal(updates.has(17), false);
    });
}

test('uncertain result remains visible with only allowlisted runtime diagnostic', async () => {
    const response = verified();
    response.execution_result.status = 'UNKNOWN';
    response.execution_result.message = 'Cannot verify dashboard';
    response.execution_diagnostic = { verifier_version: 'services-dashboard-v2',
        result_origin: 'new_attempt', verifier_invoked: true, private_data: 'DO_NOT_RENDER' };
    const updates = await submitThroughComponent(response);
    assert.match(updates.get(10), /UNKNOWN.*services-dashboard-v2; new_attempt; verifier invoked/);
    assert.doesNotMatch(updates.get(10), /DO_NOT_RENDER/);
    assert.equal(updates.has(14), false);
});


for (const [current, next] of Object.entries({stage_1a_otp:'stage_1b_login', stage_1b_login:'stage_2_service',
        stage_2_service:'stage_3_address', stage_3_address:'stage_4_document', stage_4_document:'stage_5_review'})) {
    test(`${current}: only fresh verified evidence advances to ${next}`, () => {
        const response = {completed_stage:current, current_stage:next, stage_info:{id:next},
            execution_result:{status:'VERIFIED_SUCCESS', message:'Observed', verification_evidence:'Fixture state'}};
        assert.equal(interpretExecutionStep(response, current).completed, true);
        for (const status of ['FAILED','NEEDS_USER','BLOCKED','UNKNOWN']) {
            assert.equal(interpretExecutionStep({...response, execution_result:{...response.execution_result,status}}, current).completed, false);
        }
        assert.equal(interpretExecutionStep({...response,execution_uncertain:true}, current).completed, false);
        assert.equal(interpretExecutionStep({...response,execution_diagnostic:{result_origin:'retained'}}, current).completed, false);
        assert.equal(interpretExecutionStep({...response,completed_stage:'obsolete_stage'}, current).completed, false);
    });
}


test('diagnostic remains reachable on the permitted origin without a reload/query flag', () => {
    const actual = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8');
    const expression = actual.match(/const inspectionEnabled = ([^;]+);/)[1];
    for (const [origin, expected] of [['http://localhost:5173', true], ['http://127.0.0.1:5173', false], ['https://unrelated.example', false]]) {
        assert.equal(vm.runInNewContext(expression, {location: {origin, search: ''}}), expected);
    }
});


test('verified address-page arrival advances Step 3 independently of form readiness', async () => {
    const response = {
        completed_stage: 'stage_2_service', current_stage: 'stage_3_address',
        stage_info: {id: 'stage_3_address'}, execution_uncertain: false,
        execution_result: {status: 'VERIFIED_SUCCESS', message: 'Destination verified; form readiness remains unchecked', verification_evidence: 'Official path and documented visible sections in authenticated session'},
    };
    assert.equal(interpretExecutionStep(response, 'stage_2_service').completed, true);
    response.execution_result.status = 'UNKNOWN';
    assert.equal(interpretExecutionStep(response, 'stage_2_service').completed, false);
    response.execution_result.status = 'VERIFIED_SUCCESS';
    response.execution_uncertain = true;
    assert.equal(interpretExecutionStep(response, 'stage_2_service').completed, false);
});


test('actual Step 4 handler requires explicit house/street before calling API', async () => {
    const updates = await submitThroughComponent({}, false, 'stage_3_address');
    assert.equal(updates.has('submittedInputs'), false);
    assert.match(updates.get(10), /Confirm House/);
});

test('actual Step 4 handler sends the approved structured inputs unchanged', async () => {
    const fields = {house_no: 'no.910', street: 'race course', locality: 'Citizen-confirmed area', pincode: '641018', new_address: 'no.910, race course, coimbatore'};
    const response = {completed_stage: 'stage_3_address', current_stage: 'stage_4_document', stage_info: {id: 'stage_4_document'}, execution_uncertain: false,
        execution_result: {status: 'VERIFIED_SUCCESS', message: 'Readback and upload-page arrival verified', verification_evidence: 'Fixture portal evidence'}};
    const updates = await submitThroughComponent(response, false, 'stage_3_address', fields);
    assert.deepEqual(updates.get('submittedInputs'), fields);
    assert.equal(updates.get(14).id, 'stage_4_document');
});


test('readiness failure identifies the actual verifier without advancing or dispatching again', async () => {
    const fields = {house_no:'Confirmed house', street:'Confirmed street', locality:'', pincode:'641025', new_address:'Confirmed address'};
    const response = {current_stage:'stage_3_address', execution_uncertain:false, retry_permitted:true,
        execution_result:{status:'UNKNOWN',message:'A unique visible enabled house control was not found'},
        execution_diagnostic:{verifier_version:'services-dashboard-v2',stage_verifier:'stage_3_address',result_origin:'new_attempt',verifier_invoked:true,verification_check:'address_form_readiness'}};
    const updates = await submitThroughComponent(response,false,'stage_3_address',fields);
    assert.match(updates.get(10), /verifier invoked; checking address form readiness/);
    assert.equal(updates.has(14),false);
    assert.equal(updates.has(15),false);
});
