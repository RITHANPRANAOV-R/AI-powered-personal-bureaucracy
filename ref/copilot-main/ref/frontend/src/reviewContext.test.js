import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

async function fixture() {
    const api = await import(`./documentApi.js?review-test=${Math.random()}`);
    const secret = 'synthetic-secret-never-printed';
    const reference = { id: 'public-context', generation: 1, input_revision: 0, result_binding: 'stored-result' };
    const context = { session_id: 'execution-server', review_context: reference, facts: { pincode: { value: '641025' } } };
    const reviewed = { confirmed_context: context, review_reference: reference, confirmed_data: { address_resolution: {
        status: 'resolved', post_office: { status: 'resolved', value: 'Alpha Office' }, conflicts: [] } },
        resolver_projection: { eligible: true, post_office: 'Alpha Office' } };
    const calls = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options = {}) => {
        const body = typeof options.body === 'string' ? JSON.parse(options.body) : null;
        calls.push({ url, headers: options.headers, body });
        const value = body?.action === 'cancel' ? { status: 'revoked' } : url.endsWith('/confirm') ? { ...reviewed, review_capability: secret }
            : url.endsWith('/launch-uidai') ? { status: 'active', current_stage: 'stage_3_address', execution_state_version: 0 } : reviewed;
        return { ok: true, status: 200, json: async () => structuredClone(value) };
    };
    return { api, secret, reference, context, calls, restore() { globalThis.fetch = original; } };
}

test('capability remains in memory; lookup and review do not confirm; distinct action binds reference', async () => {
    const f = await fixture();
    try {
        const review = await f.api.confirmAadhaarDocument({}, {}, 'client', { resolve_address: true });
        assert.equal(f.calls.length, 3);
        assert.equal(f.calls[0].body.resolve_address, undefined);
        assert.equal(f.calls[1].body.confirm_resolver_projection, undefined);
        assert.equal(f.calls[2].headers.Authorization === `Bearer ${f.secret}`, true);
        assert.equal(JSON.stringify(review).includes(f.secret), false);
        await f.api.confirmAadhaarDocument({}, {}, 'client', { confirm_resolver_projection: true, review_reference: f.reference });
        assert.equal(f.calls[3].body.action, 'confirm_post_office');
        assert.deepEqual(f.calls[3].body.review_reference, f.reference);
        assert.equal(f.calls[3].body.address_resolution, undefined);
        await f.api.launchUidaiBrowser(f.context);
        await f.api.submitBrowserStep('client', true, '', { pincode: '641025' });
        await f.api.getFinalReview('client');
        await f.api.finalReviewAction('client', 'Approve & Submit', 'final-binding');
        for (const call of f.calls.slice(1)) {
            assert.equal(call.headers.Authorization === `Bearer ${f.secret}`, true);
            assert.equal(call.url.includes(f.secret), false);
            assert.equal(JSON.stringify(call.body).includes(f.secret), false);
        }
        assert.equal(f.calls.find(c => c.url.endsWith('/submit-step')).body.session_id, 'execution-server');
        assert.equal(f.calls.find(c => c.url.endsWith('/submit-step')).body.user_inputs.pincode, '641025');
        assert.equal(f.calls.at(-1).body.action, 'Approve & Submit');
    } finally { f.restore(); }
});

test('cancellation revokes and forgets capability; unrelated session cannot use it', async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        assert.throws(() => f.api.getFinalReview('unrelated'), /Confirm a new/);
        await f.api.cancelResolverReview('client');
        assert.equal(f.calls.at(-1).body.action, 'cancel');
        assert.throws(() => f.api.getFinalReview('client'), /Confirm a new/);
    } finally { f.restore(); }
});

test('no capability persistence, logging, URL encoding or context export', () => {
    const source = readFileSync(new URL('./documentApi.js', import.meta.url), 'utf8');
    assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|document\.cookie|console\./);
    assert.match(source, /delete response\.review_capability/);
    assert.match(source, /const reviews = new Map/);
});

test('explicit UI action requires exact server-published reference', () => {
    const { transformSync } = createRequire(import.meta.url)('esbuild');
    const source = readFileSync(new URL('./AadhaarAssistant.jsx', import.meta.url), 'utf8');
    const context = vm.createContext({ module: { exports: {} }, require: () => ({}) });
    vm.runInContext(transformSync(source, { loader: 'jsx', format: 'cjs' }).code, context);
    const options = context.module.exports.resolverRequestOptions;
    const review = { resolver_projection: { eligible: true }, confirmed_data: { address_resolution: {
        status: 'resolved', post_office: { status: 'resolved' }, conflicts: [] } } };
    assert.throws(() => options('confirm_post_office', review), /published/);
    review.review_reference = { id: 'server', generation: 2, input_revision: 1, result_binding: 'exact' };
    const confirmed = options('confirm_post_office', review);
    assert.equal(confirmed.confirm_resolver_projection, true);
    assert.equal(confirmed.address_resolution, undefined);
    assert.equal(confirmed.review_reference, review.review_reference);
    assert.equal(options('resolve').confirm_resolver_projection, undefined);
    assert.equal(options('continue_without_projection', review).confirm_resolver_projection, undefined);
});


function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}
function response(payload, status = 200) {
    return { ok: status < 400, status, json: async () => structuredClone(payload) };
}

for (const failure of [
    { detail: { code: 'REVIEW_CAPABILITY_AUTH_FAILED', message: 'Invalid capability' } },
    { detail: 'Frontend origin is not permitted.' },
    { detail: { code: 'OTHER_FORBIDDEN', message: 'Not permitted' } },
]) test(`typed authentication recovery distinguishes ${typeof failure.detail === 'string' ? 'origin' : failure.detail.code}`, async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        // A separately issued capability must not be forgotten.
        globalThis.fetch = async () => response({ confirmed_context: { session_id: 'other-server', review_context: { id: 'other' }, facts: {} }, review_capability: 'other-synthetic' });
        await f.api.confirmAadhaarDocument({}, {}, 'other-client');
        globalThis.fetch = async () => response(failure, 403);
        await assert.rejects(f.api.getFinalReview('client'), error => error.status === 403
            && error.code === (typeof failure.detail === 'object' ? failure.detail.code : undefined));
        if (failure.detail?.code === 'REVIEW_CAPABILITY_AUTH_FAILED') {
            assert.throws(() => f.api.getFinalReview('client'), /Confirm a new/);
            assert.throws(() => f.api.getFinalReview('execution-server'), /Confirm a new/);
        } else {
            await assert.rejects(f.api.getFinalReview('client'), error => error.status === 403);
        }
        globalThis.fetch = async () => response({});
        await f.api.getFinalReview('other-client');
        await f.api.getFinalReview('other-server');
    } finally { f.restore(); }
});

for (const kind of ['network', 'rejected', 'unreadable', 'missing-acknowledgement']) test(`cancellation forgets aliases immediately despite ${kind} outcome`, async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        const pending = deferred();
        globalThis.fetch = () => pending.promise;
        const cancelled = f.api.cancelResolverReview('client');
        const rejected = assert.rejects(cancelled, error => error.code === 'REVIEW_REVOCATION_UNCONFIRMED');
        assert.throws(() => f.api.getFinalReview('client'), /Confirm a new/);
        assert.throws(() => f.api.getFinalReview('execution-server'), /Confirm a new/);
        if (kind === 'network') pending.reject(new Error('Transport lost'));
        else if (kind === 'rejected') pending.resolve(response({ detail: 'Rejected' }, 409));
        else if (kind === 'missing-acknowledgement') pending.resolve(response({}));
        else pending.resolve({ ok: false, status: 502, json: async () => { throw new Error('Unreadable'); } });
        await rejected;
    } finally { f.restore(); }
});

for (const change of ['cancel', 'correction', 'extraction']) test(`late resolver response after ${change} is ignored`, async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        const originalFetch = globalThis.fetch;
        const pending = deferred(), started = deferred();
        globalThis.fetch = (url, options) => {
            if (url.endsWith('/resolve')) { started.resolve(); return pending.promise; }
            return originalFetch(url, options);
        };
        const lookup = f.api.confirmAadhaarDocument({}, {}, 'client', { resolve_address: true });
        const rejected = assert.rejects(lookup, error => error.code === 'STALE_REVIEW_OPERATION');
        await started.promise;
        if (change === 'cancel') await f.api.cancelResolverReview('client');
        if (change === 'correction') {
            f.api.invalidateResolverOperation('client');
            await f.api.confirmAadhaarDocument({}, { pincode: '560001' }, 'client');
        }
        if (change === 'extraction') await f.api.extractAadhaarDocument(new Blob(['synthetic']));
        const count = f.calls.length;
        pending.resolve(response({}));
        await rejected;
        assert.equal(f.calls.length, count); // No stale follow-up publication request.
        if (change !== 'correction') assert.throws(() => f.api.getFinalReview('client'), /Confirm a new/);
    } finally { f.restore(); }
});

test('late initial capability issuance cannot repopulate cancelled credentials', async () => {
    const f = await fixture();
    try {
        const pending = deferred();
        globalThis.fetch = () => pending.promise;
        const creation = f.api.confirmAadhaarDocument({}, {}, 'client');
        const rejected = assert.rejects(creation, error => error.code === 'STALE_REVIEW_OPERATION');
        await assert.rejects(f.api.cancelResolverReview('client'), /revocation could not be confirmed/);
        pending.resolve(response({ review_capability: 'synthetic-late', confirmed_context: f.context }));
        await rejected;
        assert.throws(() => f.api.getFinalReview('client'), /Confirm a new/);
    } finally { f.restore(); }
});


test('late publication GET cannot restore a cancelled review', async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        const originalFetch = globalThis.fetch;
        const pending = deferred(), started = deferred();
        globalThis.fetch = (url, options) => {
            if (url.endsWith('/review')) { started.resolve(); return pending.promise; }
            return originalFetch(url, options);
        };
        const lookup = f.api.confirmAadhaarDocument({}, {}, 'client', { resolve_address: true });
        const rejected = assert.rejects(lookup, error => error.code === 'STALE_REVIEW_OPERATION');
        await started.promise;
        await f.api.cancelResolverReview('client');
        pending.resolve(response({ confirmed_context: f.context, review_reference: f.reference }));
        await rejected;
        assert.throws(() => f.api.getFinalReview('execution-server'), /Confirm a new/);
    } finally { f.restore(); }
});


test('structural inspection uses existing capability and never dispatches an execution attempt', async () => {
    const f = await fixture();
    try {
        await f.api.confirmAadhaarDocument({}, {}, 'client');
        await f.api.inspectBrowserStructure('client');
        const call = f.calls.at(-1);
        assert.equal(call.url.endsWith('/api/browser/inspect-structure'), true);
        assert.deepEqual(call.body, {session_id:'execution-server'});
        assert.equal(call.headers.Authorization === `Bearer ${f.secret}`, true);
        assert.equal(call.url.includes(f.secret), false);
        assert.equal(f.calls.some(c=>c.url.endsWith('/submit-step')||c.url.endsWith('/launch-uidai')), false);
    } finally { f.restore(); }
});
