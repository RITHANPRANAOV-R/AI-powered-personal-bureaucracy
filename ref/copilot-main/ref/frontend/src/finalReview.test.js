import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import { interpretExecutionStep } from './executionStepState.js';

const require = createRequire(import.meta.url);
const { transformSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8');
const review = () => ({ state: 'REVIEW_READY', binding: 'synthetic-binding', unknown_fields: ['current_values'], blocking_reasons: [], package: {
    service: 'Synthetic service', citizen_information: { name: { value: 'Synthetic Citizen', provenance: 'user_confirmed' } },
    extracted_document_information: 'Synthetic extraction', corrected_information: 'Corrected value', current_values: 'UNKNOWN',
    new_values: 'New value', address: 'Synthetic address', pincode: '110001', supporting_documents: ['synthetic.pdf'],
    document_type: 'Synthetic document type', requirements: ['Synthetic requirement'], fees: 'Synthetic fee',
    declarations: [{ statement: 'Synthetic consent', agreed: true }], warnings: ['Synthetic limitation'],
    upload_validation: 'UNKNOWN', submission_validation: 'UNKNOWN',
} });

function load(react = React, api = {}, expose = false) {
    const context = vm.createContext({ React: react, module: { exports: {} }, require(name) {
        if (name === 'react') return react;
        if (name === 'lucide-react') return {};
        if (name === './executionStepState') return { interpretExecutionStep };
        if (name === './documentApi') return api;
        throw new Error(`Unexpected import: ${name}`);
    } });
    const input = expose ? source.replace('    const isBusy =', '    globalThis.handlers = { openFinalReview, handleFinalReviewAction, handleAppSubmitStep };\n    const isBusy =') : source;
    vm.runInContext(transformSync(input, { loader: 'jsx', format: 'cjs' }).code, context);
    return context;
}
const Panel = load().module.exports.FinalReviewPanel;
const props = (value = review()) => ({ review: value, busy: false, onApprove() {}, onEdit() {}, onCancel() {} });

test('final review displays every submission group, values, provenance and UNKNOWN', () => {
    const html = renderToStaticMarkup(React.createElement(Panel, props()));
    for (const text of ['FINAL REVIEW', 'Service', 'Information', 'Documents', 'Requirements', 'Declarations', 'Warnings',
        'Synthetic Citizen', 'user_confirmed', 'Synthetic extraction', 'Corrected value', 'New value', 'Synthetic address',
        '110001', 'synthetic.pdf', 'Synthetic document type', 'Synthetic requirement', 'Synthetic fee', 'Synthetic consent', 'Synthetic limitation', 'UNKNOWN']) {
        assert.ok(html.includes(text), text);
    }
    assert.equal((html.match(/<button/g) || []).length, 3);
    assert.ok(html.includes('Edit / Correct'));
    assert.ok(html.includes('Approve &amp; Submit'));
    assert.ok(html.includes('Cancel'));
});

for (const state of ['REVIEW_REQUIRED', 'APPROVAL_INVALIDATED', 'APPROVED']) {
    test(`${state} disables explicit approval`, () => {
        const value = review(); value.state = state;
        const html = renderToStaticMarkup(React.createElement(Panel, props(value)));
        assert.match(html, /<button[^>]*disabled[^>]*>Approve &amp; Submit/);
    });
}
test('blocking reason and pending request disable approval', () => {
    const value = review(); value.blocking_reasons = ['Required upload is UNKNOWN'];
    assert.match(renderToStaticMarkup(React.createElement(Panel, props(value))), /<button[^>]*disabled[^>]*>Approve &amp; Submit/);
    assert.match(renderToStaticMarkup(React.createElement(Panel, { ...props(), busy: true })), /<button[^>]*disabled[^>]*>Approve &amp; Submit/);
});

test('rendering cannot approve; explicit button carries exact reviewed binding', () => {
    let approved = null;
    const tree = Panel({ ...props(), onApprove(value) { approved = value; } });
    assert.equal(approved, null);
    const buttons = React.Children.toArray(tree.props.children).filter(child => child.type === 'button');
    buttons[1].props.onClick();
    assert.equal(approved, 'synthetic-binding');
});

test('empty objects and missing review visibly preserve UNKNOWN', () => {
    const value = review(); value.package.corrected_information = {};
    assert.ok(renderToStaticMarkup(React.createElement(Panel, props(value))).includes('UNKNOWN'));
    assert.ok(renderToStaticMarkup(React.createElement(Panel, props(null))).includes('Approval is unavailable'));
});

function handlers(response = {}, pending = false) {
    let index = 0;
    const updates = new Map();
    const calls = [];
    const initial = new Map([[0, 3], [13, true], [14, { id: 'stage_5_review' }], [18, pending]]);
    const operationRef = { current: 0 };
    const react = { useRef() { return operationRef; }, useState(value) {
        const key = index++;
        return [initial.has(key) ? initial.get(key) : value, value => updates.set(key, value)];
    }, createElement() { return null; } };
    const api = {
        getFinalReview: async () => { calls.push('review'); return { final_review: review() }; },
        finalReviewAction: async (session, action, binding) => { calls.push({ action, binding }); return response; },
        submitBrowserStep: async () => { calls.push('generic-submit'); return response; },
    };
    const context = load(react, api, true);
    context.module.exports.default();
    return { ...context.handlers, updates, calls };
}

test('generic final-stage button opens review without submitting or approving', async () => {
    const fixture = handlers();
    await fixture.handleAppSubmitStep();
    assert.deepEqual(fixture.calls, ['review']);
    assert.equal(fixture.updates.has(17), false);
});
for (const action of ['Edit / Correct', 'Cancel']) {
    test(`${action} sends distinct invalidation and never submits`, async () => {
        const fixture = handlers();
        await fixture.handleFinalReviewAction(action);
        assert.equal(fixture.calls.length, 1);
        assert.equal(fixture.calls[0].action, action);
        assert.equal(fixture.updates.get(19), null);
        if (action === 'Edit / Correct') { assert.equal(fixture.updates.get(0), 2); assert.equal(fixture.updates.get(6), true); }
        assert.equal(fixture.updates.has(17), false);
    });
}
for (const status of ['UNKNOWN', 'BLOCKED', 'FAILED', 'NEEDS_USER']) {
    test(`approval HTTP 200 / ${status} cannot manufacture final success`, async () => {
        const fixture = handlers({ is_completed: true, status: 'success', urn: 'synthetic-local-reference',
            execution_result: { status, message: 'Unverified fixture' } });
        await fixture.handleFinalReviewAction('Approve & Submit', 'synthetic-binding');
        assert.equal(fixture.calls[0].binding, 'synthetic-binding');
        assert.equal(fixture.calls[0].action, 'Approve & Submit');
        assert.equal(fixture.updates.has(17), false);
        assert.equal(fixture.updates.has(16), false);
        assert.match(fixture.updates.get(10), new RegExp(status));
    });
}
test('pending approval blocks concurrent requests', async () => {
    const fixture = handlers({}, true);
    await fixture.handleFinalReviewAction('Approve & Submit', 'synthetic-binding');
    assert.equal(fixture.calls.length, 0);
});
