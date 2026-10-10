import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import { confirmAadhaarDocument } from './documentApi.js';
const require = createRequire(import.meta.url);
const { transformSync } = require('esbuild');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8');
function load(react = React, api = {}, expose = false) {
    const context = vm.createContext({ module: { exports: {} }, require(name) {
        if (name === 'react') return react;
        if (name === 'lucide-react') return new Proxy({}, { get() { return () => null; } });
        if (name === './documentApi') return api;
        return {};
    }});
    const input = expose ? source.replace('    const isBusy =', '    globalThis.handlers = { requestResolution, confirmDetails, saveCorrection, cancelProjectionReview, handleFile, startInteractiveSession, confirmReviewedDetails };\n    const isBusy =') : source;
    vm.runInContext(transformSync(input, { loader: 'jsx', format: 'cjs' }).code, context);
    return context;
}
const exported = load().module.exports;
function reviewed() { return { review_reference: { id: 'server-review', input_revision: 0, generation: 1, result_binding: 'exact' }, resolver_projection: { eligible: true, post_office: 'Alpha Office' },
    confirmed_data: { address_resolution: { status: 'resolved', queried_pin: '641025', conflicts: [],
        post_office: { status: 'resolved', value: 'Alpha Office' }, candidates: [{ office_name: 'Alpha Office' }],
        evidence: [{ passage: 'Official-shaped evidence', source: { url: 'https://api.data.gov.in/' } }] } } }; }
function buttons(tree) {
    if (!tree || typeof tree !== 'object') return [];
    return [ ...(tree.type === 'button' ? [tree] : []), ...React.Children.toArray(tree.props?.children).flatMap(buttons) ];
}
test('review rendering is not confirmation; only distinct button invokes confirmation', () => {
    let confirmed = 0;
    const props = { review: reviewed(), busy: false, onResolve() {}, onCancel() {}, onConfirm() { confirmed++; } };
    const tree = exported.ResolverReviewPanel(props);
    assert.equal(confirmed, 0);
    const html = renderToStaticMarkup(React.createElement(exported.ResolverReviewPanel, props));
    for (const label of ['641025', 'Alpha Office', 'Official-shaped evidence', 'candidates', 'conflicts', 'No candidate is selected automatically']) assert.ok(html.includes(label));
    const button = buttons(tree).find(b => b.props.children === 'Use this Post Office & continue');
    assert.equal(button.props.disabled, false);
    button.props.onClick();
    assert.equal(confirmed, 1);
});
for (const status of ['ambiguous', 'conflict', 'unavailable', 'no_result']) test(`${status} review cannot confirm`, () => {
    const review = reviewed(); review.confirmed_data.address_resolution.status = status; review.resolver_projection.eligible = false;
    assert.throws(() => exported.resolverRequestOptions('confirm_post_office', review), /eligible/);
    const html = renderToStaticMarkup(React.createElement(exported.ResolverReviewPanel, { review, busy: false }));
    assert.match(html, /<button[^>]*disabled[^>]*>Use this Post Office/);
});
test('missing explicit action, unresolved PO and missing eligibility cannot authorize', () => {
    assert.throws(() => exported.resolverRequestOptions(undefined, reviewed()), /Explicit/);
    const value = reviewed(); value.confirmed_data.address_resolution.post_office.status = 'unresolved';
    assert.throws(() => exported.resolverRequestOptions('confirm_post_office', value), /eligible/);
    assert.throws(() => exported.resolverRequestOptions('confirm_post_office', null), /eligible/);
    assert.equal(exported.resolverRequestOptions('resolve').confirm_resolver_projection, undefined);
    assert.equal(exported.resolverRequestOptions('continue_without_projection', reviewed()).confirm_resolver_projection, undefined);
});
test('API request sequence carries true flag only for distinct confirmation', async () => {
    const calls = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
        const body = options.body ? JSON.parse(options.body) : null;
        calls.push({ url, body, headers: options.headers });
        const response = { ...reviewed(), confirmed_context: { session_id: 'execution-fixture', review_context: { id: 'server-review' }, facts: {} } };
        if (url.endsWith('/confirm')) response.review_capability = 'synthetic-capability';
        return { ok: true, json: async () => response };
    };
    try {
        await confirmAadhaarDocument({}, {}, 'fixture');
        const review = await confirmAadhaarDocument({}, {}, 'fixture', exported.resolverRequestOptions('resolve'));
        assert.equal(calls.some(call => call.body?.confirm_resolver_projection === true), false);
        await confirmAadhaarDocument({}, {}, 'fixture', exported.resolverRequestOptions('confirm_post_office', review));
        const confirmation = calls.at(-1);
        assert.equal(confirmation.body.confirm_resolver_projection, true);
        assert.equal(confirmation.body.action, 'confirm_post_office');
        assert.deepEqual(confirmation.body.review_reference, review.review_reference);
        assert.equal(confirmation.body.address_resolution, undefined);
        assert.equal(confirmation.headers.Authorization, 'Bearer synthetic-capability');
    } finally { globalThis.fetch = original; }
});

function fixture(initialReview = null, failure = null, overrides = {}) {
    let values = [], index = 0;
    const calls = [];
    const operationRef = { current: 0 };
    const react = { useRef() { return operationRef; }, createElement() { return null; }, useState(value) {
        const slot = index++;
        if (!(slot in values)) values[slot] = value;
        return [values[slot], next => { values[slot] = typeof next === 'function' ? next(values[slot]) : next; }];
    }};
    const context = load(react, {
        invalidateResolverOperation() {},
        async confirmAadhaarDocument(extraction, corrections, id, options) { calls.push(options); if (failure && options?.confirm_resolver_projection) throw new Error(failure); return { ...reviewed(), confirmed_context: { session_id: id, facts: {
            pincode: { value: '641025' }, new_address: { value: '12 ABC Street, Tamil Nadu 641025' },
            ...(options?.confirm_resolver_projection ? { post_office: { value: 'Alpha Office', resolution_projection: {} } } : {}) } } }; },
        async launchUidaiBrowser(ctx) { calls.push({ launch: ctx }); return {}; },
        ...overrides,
    }, true);
    function render() { index = 0; context.module.exports.default(); }
    render();
    if (initialReview) { values[values.length - 1] = initialReview; render(); }
    return { context, calls, render, values };
}
test('normal handlers resolve without launch; separate confirmation launches projected context', async () => {
    const f = fixture();
    await f.context.handlers.requestResolution(); f.render();
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].resolve_address, true);
    await f.context.handlers.confirmDetails('confirm_post_office');
    assert.equal(f.calls[1].confirm_resolver_projection, true);
    assert.equal(f.calls[2].launch.facts.post_office.value, 'Alpha Office');
    const inputs = f.values.find(v => v && v.pincode === '641025' && 'house_no' in v);
    assert.equal(inputs.house_no, ''); assert.equal(inputs.locality, '');
});
test('correction clears review and prevents stale confirmation before any API request', async () => {
    const f = fixture(reviewed());
    f.values[8] = 'Corrected address'; f.render();
    f.context.handlers.saveCorrection(); f.render();
    await f.context.handlers.confirmDetails('confirm_post_office');
    assert.equal(f.calls.length, 0);
});
test('continuing without projection excludes reviewed metadata and explicit flag', async () => {
    const f = fixture(reviewed());
    await f.context.handlers.confirmDetails();
    assert.equal(f.calls[0].confirm_resolver_projection, undefined);
    assert.equal(f.calls[0].address_resolution, undefined);
    assert.equal(f.calls[1].launch.facts.post_office, undefined);
});

test('backend stale-result error is visible and never launches a browser', async () => {
    const f = fixture(reviewed(), 'Stale or ineligible projection');
    await f.context.handlers.confirmDetails('confirm_post_office');
    assert.equal(f.calls.length, 1);
    assert.equal(f.values[10], 'Stale or ineligible projection');
});
test('pending request prevents resolution, confirmation and correction handlers', async () => {
    const f = fixture(reviewed()); f.values[9] = 'confirming'; f.values[8] = 'Corrected address'; f.render();
    await f.context.handlers.requestResolution();
    await f.context.handlers.confirmDetails('confirm_post_office');
    f.context.handlers.saveCorrection();
    assert.equal(f.calls.length, 0);
    assert.equal(f.values[f.values.length - 1].resolver_projection.eligible, true);
});
test('cancel review clears selection and cannot imply projection authorization', () => {
    let review = reviewed(); let confirmations = 0;
    const tree = exported.ResolverReviewPanel({ review, busy: false, onCancel() { review = null; }, onConfirm() { confirmations++; } });
    buttons(tree).find(b => b.props.children === 'Cancel Post Office lookup').props.onClick();
    assert.equal(review, null); assert.equal(confirmations, 0);
    assert.throws(() => exported.resolverRequestOptions('confirm_post_office', review), /eligible/);
});


function delayed() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

test('UI cancellation clears review immediately and reports unconfirmed revocation', async () => {
    const pending = delayed();
    const f = fixture(reviewed(), null, { cancelResolverReview: () => pending.promise });
    const action = f.context.handlers.cancelProjectionReview();
    assert.equal(f.values[f.values.length - 1], null);
    pending.reject(new Error('Local review cleared. Server-side revocation could not be confirmed.'));
    await action;
    assert.match(f.values[10], /revocation could not be confirmed/);
});

for (const change of ['cancel', 'extraction']) test(`UI ignores late review after ${change}`, async () => {
    const pending = delayed();
    const f = fixture(null, null, {
        confirmAadhaarDocument: () => pending.promise,
        cancelResolverReview: async () => {},
        extractAadhaarDocument: async () => ({ status: 'success', data: {} }),
    });
    const lookup = f.context.handlers.requestResolution();
    if (change === 'cancel') await f.context.handlers.cancelProjectionReview();
    else await f.context.handlers.handleFile({ name: 'synthetic' });
    pending.resolve(reviewed());
    await lookup;
    assert.equal(f.values[f.values.length - 1], null);
    assert.equal(f.calls.length, 0);
});


for (const projected of [false, true]) test(`confirmed context owns address inputs with projection=${projected}`, async () => {
    const canonical = { session_id: 'server', facts: {
        pincode: { value: '641025' }, new_address: { value: '12 ABC Street, Tamil Nadu 641025' },
        ...(projected ? { post_office: { value: 'Alpha Office', resolution_projection: {} } } : {}),
    } };
    const f = fixture();
    await f.context.handlers.startInteractiveSession(canonical);
    const mapped = f.values.find(v => v && typeof v === 'object' && 'pincode' in v && 'house_no' in v);
    assert.equal(mapped.pincode, '641025');
    assert.equal(mapped.new_address, canonical.facts.new_address.value);
    assert.equal(f.calls[0].launch, canonical);
});

for (const status of ['encrypted_document', 'malformed_document', 'extraction_failed', 'unsupported_document']) test(`upload displays backend ${status} error`, async () => {
    const message = `Backend processing error: ${status}`;
    const f = fixture(null, null, { extractAadhaarDocument: async () => ({ status, error: message }) });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    assert.equal(f.values[10], message);
    assert.equal(f.values[9], 'error');
});

test('upload retains successful backend extraction response', async () => {
    const response = { status: 'success', data: { name: { value: 'Synthetic Citizen' } }, pages: [{ page_number: 1 }] };
    const f = fixture(null, null, { extractAadhaarDocument: async () => response });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    assert.ok(f.values.includes(response));
    assert.equal(f.values[9], 'idle');
    assert.equal(f.values[10], '');
});

test('readable document with missing fields retains evidence and displays correction warning', async () => {
    const response = { status: 'missing_required_fields', data: {}, warnings: ['Correct the missing address.'] };
    const f = fixture(null, null, { extractAadhaarDocument: async () => response });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    assert.ok(f.values.includes(response));
    assert.equal(f.values[9], 'idle');
    assert.equal(f.values[10], 'Correct the missing address.');
});


test('address review renders separate current address, proposed address and new PIN', () => {
    const data = { existing_address: { value: 'Old Street 638106' }, new_address: { value: 'no.456, race course, coimbatore-641018' }, pincode: { value: '641018' } };
    let edited;
    const props = { data, onCorrect(key) { edited = key; }, busy: false };
    const html = renderToStaticMarkup(React.createElement(exported.AddressReview, props));
    for (const text of ['Current Address', '638106', 'New Address (to update)', 'coimbatore-641018', 'PIN Code', 'Change']) assert.ok(html.includes(text));
    assert.ok(!html.includes('projection'));
    buttons(exported.AddressReview(props)).find(b => b.props['aria-label'] === 'Change PIN Code').props.onClick();
    assert.equal(edited, 'pincode');
    assert.equal(data.existing_address.value, 'Old Street 638106');
});

test('new PIN 641018 and new address reach canonical frontend mapping unchanged', async () => {
    const canonical = { session_id: 'server', facts: { existing_address: { value: 'Old Street 638106' }, new_address: { value: 'no.456, race course, coimbatore-641018' }, pincode: { value: '641018' } } };
    const f = fixture();
    await f.context.handlers.startInteractiveSession(canonical);
    const mapped = f.values.find(v => v && typeof v === 'object' && 'pincode' in v && 'house_no' in v);
    assert.equal(mapped.pincode, '641018');
    assert.equal(mapped.new_address, canonical.facts.new_address.value);
    assert.equal(f.calls[0].launch, canonical);
});


test('request parsing compares PINs inside proposed address rather than current address', () => {
    const result = exported.extractAddressRequest('Current address: Old Street 638106. New address: no.456, race course, coimbatore-641018');
    assert.equal(result.pincode, '641018');
    assert.equal(result.newAddress, 'no.456, race course, coimbatore-641018');
    assert.throws(() => exported.extractAddressRequest('New address: New street 641018 or 641025'), /Multiple PIN/);
});


function completeExtraction() { return { status: 'success', data: { name: { value: 'Synthetic Citizen' }, date_of_birth: { value: '01/01/2000' }, existing_address: { value: 'Old Street 638106' }, new_address: { value: 'no.456, race course, coimbatore-641018' }, pincode: { value: '641018' } } }; }

test('review screen reuses one compact card and hides lookup workflow controls', () => {
    let index = 0;
    const react = { ...React, useRef: () => ({ current: 0 }), useState(initial) {
        const slot = index++;
        return [slot === 0 ? 2 : slot === 3 ? completeExtraction() : initial, () => {}];
    } };
    const component = load(react).module.exports.default;
    const html = renderToStaticMarkup(React.createElement(component));
    assert.equal((html.match(/class="details-card"/g) || []).length, 1);
    for (const text of ['Current Address', '638106', 'New Address (to update)', 'coimbatore-641018', 'PIN Code', '641018', 'Edit or Add Field', 'Confirm details']) assert.ok(html.includes(text));
    for (const text of ['Check Post Office (optional)', 'Look up Post Office options', 'Optional Post Office resolution', 'Address update review', 'publication', 'projection']) assert.ok(!html.includes(text));
    const tags = html.match(/<button\b[^>]*>/g) || [];
    assert.ok(tags.length > 0);
    assert.ok(tags.every(tag => /class="(?:text-button detail-edit|text-button|primary-button|secondary-button|back-button|step-node|scrim)/.test(tag)), tags.join(' '));
});

test('internal lookup prepares review but never confirms or launches automatically', async () => {
    const response = completeExtraction();
    const f = fixture(null, null, { extractAadhaarDocument: async () => response });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].resolve_address, true);
    assert.equal(f.calls[0].confirm_resolver_projection, undefined);
    assert.equal(f.values[f.values.length - 2], false);
    assert.ok(f.values.includes(response));
});

test('compact Post Office choice remains explicit and uses exact existing confirmation contract', async () => {
    const f = fixture(reviewed());
    assert.equal(f.values[f.values.length - 2], false);
    const row = exported.ReviewDetails({ data: completeExtraction().data, review: reviewed(), includePostOffice: false,
        onCorrect() {}, onPostOfficeChoice(value) { f.values[f.values.length - 2] = value; } });
    function inputs(node) { if (!node || typeof node !== 'object') return []; return [...(node.type === 'input' ? [node] : []), ...React.Children.toArray(node.props?.children).flatMap(inputs)]; }
    const checkbox = inputs(row)[0];
    assert.equal(checkbox.props.checked, false);
    assert.equal(f.calls.length, 0);
    checkbox.props.onChange({ target: { checked: true } });
    f.render();
    await f.context.handlers.confirmReviewedDetails();
    assert.equal(f.calls[0].confirm_resolver_projection, true);
    assert.equal(f.calls[0].review_reference, f.values[f.values.length - 1].review_reference);
    assert.equal(f.calls[1].launch.facts.post_office.value, 'Alpha Office');
});

test('ordinary compact confirmation continues without automatically choosing Post Office', async () => {
    const f = fixture(reviewed());
    await f.context.handlers.confirmReviewedDetails();
    assert.equal(f.calls[0].confirm_resolver_projection, undefined);
    assert.equal(f.calls[1].launch.facts.post_office, undefined);
});

test('ambiguous Post Office renders no selectable or executable option', () => {
    const review = reviewed(); review.resolver_projection.eligible = false; review.confirmed_data.address_resolution.status = 'ambiguous';
    const html = renderToStaticMarkup(React.createElement(exported.ReviewDetails, { data: completeExtraction().data, review, onCorrect() {} }));
    assert.ok(html.includes('No option selected'));
    assert.ok(!html.includes('type="checkbox"'));
    assert.throws(() => exported.resolverRequestOptions('confirm_post_office', review), /eligible/);
});

test('lookup failure preserves extraction and new address instead of substituting source PIN', async () => {
    const response = completeExtraction();
    const f = fixture(null, null, { extractAadhaarDocument: async () => response, confirmAadhaarDocument: async () => { throw new Error('Network unavailable'); } });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    await new Promise(resolve => setImmediate(resolve));
    assert.ok(f.values.includes(response));
    assert.equal(response.data.pincode.value, '641018');
    assert.equal(response.data.existing_address.value, 'Old Street 638106');
    assert.match(f.values[10], /Post Office options could not be checked/);
    assert.equal(f.values[9], 'idle');
    assert.equal(f.values[f.values.length - 1], null);
});


test('valid internal lookup, explicit field approval and launch preserve exact proposed address and PIN', async () => {
    const extraction = completeExtraction();
    const calls = [];
    const review = reviewed(); review.confirmed_data.address_resolution.queried_pin = '641018';
    const f = fixture(null, null, {
        extractAadhaarDocument: async () => extraction,
        confirmAadhaarDocument: async (input, edits, id, options) => {
            calls.push(options);
            return { ...review, confirmed_context: { session_id: id, facts: {
                existing_address: { value: 'Old Street 638106' }, new_address: { value: extraction.data.new_address.value }, pincode: { value: '641018' },
                ...(options?.confirm_resolver_projection ? { post_office: { value: 'Alpha Office', resolution_projection: {} } } : {})
            } } };
        }
    });
    await f.context.handlers.handleFile({ name: 'synthetic.pdf' });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls[0].resolve_address, true);
    assert.equal(calls[0].confirm_resolver_projection, undefined);
    assert.equal(f.calls.length, 0);
    f.values[f.values.length - 2] = true;
    f.render();
    await f.context.handlers.confirmReviewedDetails();
    assert.equal(calls[1].review_reference, review.review_reference);
    assert.equal(calls[1].confirm_resolver_projection, true);
    const context = f.calls[0].launch;
    assert.equal(context.facts.pincode.value, '641018');
    assert.equal(context.facts.new_address.value, extraction.data.new_address.value);
    assert.equal(context.facts.existing_address.value, 'Old Street 638106');
    assert.equal(context.facts.post_office.value, 'Alpha Office');
});

test('correction clears prior Post Office approval and prepares a new review internally', async () => {
    const f = fixture(reviewed());
    f.values[3] = completeExtraction();
    f.values[f.values.length - 2] = true;
    f.values[7] = 'new_address'; f.values[8] = 'Corrected Street 641018'; f.render();
    f.context.handlers.saveCorrection();
    assert.equal(f.values[f.values.length - 2], false);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(f.calls[0].resolve_address, true);
    assert.equal(f.calls[0].confirm_resolver_projection, undefined);
    assert.equal(f.values[5].new_address, 'Corrected Street 641018');
    assert.equal(f.calls.length, 1);
});


for (const status of [400, 422]) test(`internal lookup preserves genuine ${status} validation errors`, async () => {
    const f = fixture(null, null, { confirmAadhaarDocument: async () => { throw Object.assign(new Error('The new PIN does not match the proposed address.'), { status }); } });
    await f.context.handlers.requestResolution();
    assert.equal(f.values[10], 'The new PIN does not match the proposed address.');
    assert.equal(f.values[9], 'error');
    assert.equal(f.calls.length, 0);
});

test('internal lookup authentication failure clears field approval and requests a fresh confirmation', async () => {
    const f = fixture(reviewed(), null, { confirmAadhaarDocument: async () => { throw Object.assign(new Error('Internal capability details'), { status: 403, code: 'REVIEW_CAPABILITY_AUTH_FAILED' }); } });
    f.values[f.values.length - 2] = true; f.render();
    await f.context.handlers.requestResolution();
    assert.equal(f.values[f.values.length - 2], false);
    assert.equal(f.values[f.values.length - 1], null);
    assert.equal(f.values[10], 'Your review session could not be verified. Confirm your details again.');
    assert.equal(f.calls.length, 0);
});
