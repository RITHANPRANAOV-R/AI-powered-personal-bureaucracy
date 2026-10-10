const API_BASE_URL = import.meta.env?.VITE_API_URL || 'http://127.0.0.1:8000';

// Scoped bearer capabilities live only in this module's memory.
const reviews = new Map();
const operations = new Map();
let extractionRevision = 0;
function forget(review) {
    review.revision = (review.revision || 0) + 1;
    for (const [key, value] of reviews) if (value === review) {
        reviews.delete(key);
        operations.set(key, {});
    }
}
export function invalidateResolverOperation(sessionId) {
    operations.set(sessionId, {});
    const review = reviews.get(sessionId);
    if (review) review.revision = (review.revision || 0) + 1;
}
function stale() {
    return Object.assign(new Error('Review operation was superseded; its response was ignored.'), { code: 'STALE_REVIEW_OPERATION' });
}
function credentials(sessionId) {
    const review = reviews.get(sessionId);
    if (!review) throw new Error('Confirm a new review context before continuing.');
    return review;
}
function scopedOptions(review, body) {
    return { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json',
        Authorization: `Bearer ${review.secret}`, 'X-Review-Context': review.id },
        ...(body ? { body: JSON.stringify(body) } : {}) };
}

async function request(path, options) {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = payload.detail;
        const error = Object.assign(new Error((typeof detail === 'string' ? detail : detail?.message)
            || payload.error || 'The assistant could not complete this step.'),
            { status: response.status, code: detail?.code || payload.code });
        if (response.status === 403 && error.code === 'REVIEW_CAPABILITY_AUTH_FAILED') {
            const id = options?.headers?.['X-Review-Context'];
            for (const review of new Set(reviews.values())) {
                if (review.id === id && options.headers.Authorization === `Bearer ${review.secret}`) forget(review);
            }
        }
        throw error;
    }
    return payload;
}

export function extractAadhaarDocument(file, userContext = {}) {
    extractionRevision += 1;
    for (const review of new Set(reviews.values())) forget(review);
    operations.clear();
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    if (userContext.newAddress) params.append('new_address', userContext.newAddress);
    if (userContext.pincode) params.append('pincode', userContext.pincode);
    const queryString = params.toString() ? `?${params.toString()}` : '';
    return request(`/api/documents/aadhaar/extract${queryString}`, {
        method: 'POST',
        body: formData,
    });
}

export async function confirmAadhaarDocument(extraction, corrections = {}, sessionId, resolverOptions = {}) {
    const ticket = {};
    operations.set(sessionId, ticket);
    const epoch = extractionRevision;
    let review = reviews.get(sessionId);
    let revision = review ? (review.revision = (review.revision || 0) + 1) : null;
    function current() {
        if (epoch !== extractionRevision || operations.get(sessionId) !== ticket
            || (review && (reviews.get(sessionId) !== review || review.revision !== revision))) throw stale();
    }
    if (!review) {
        const response = await request('/api/documents/aadhaar/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmed: true, extraction, corrections, session_id: sessionId }),
        });
        current();
        const reference = response.confirmed_context?.review_context;
        if (!reference?.id || !response.review_capability) throw new Error('Server review capability was not issued.');
        review = { id: reference.id, secret: response.review_capability,
            context: response.confirmed_context, corrections: JSON.stringify(corrections) };
        delete response.review_capability;
        revision = review.revision = 0;
        reviews.set(sessionId, review);
        reviews.set(review.context.session_id, review);
    } else if (review.corrections !== JSON.stringify(corrections)) {
        const response = await request(`/api/review-contexts/${review.id}/action`, scopedOptions(review,
            { action: 'correct', corrections }));
        current();
        review.context = response.confirmed_context;
        review.corrections = JSON.stringify(corrections);
    }
    let response;
    if (resolverOptions.resolve_address === true) {
        await request(`/api/review-contexts/${review.id}/resolve`, scopedOptions(review, {}));
        current();
        response = await request(`/api/review-contexts/${review.id}/review`, scopedOptions(review));
    } else if (resolverOptions.confirm_resolver_projection === true) {
        response = await request(`/api/review-contexts/${review.id}/action`, scopedOptions(review,
            { action: 'confirm_post_office', confirm_resolver_projection: true, review_reference: resolverOptions.review_reference }));
    } else {
        response = await request(`/api/review-contexts/${review.id}/action`, scopedOptions(review,
            { action: 'continue_without_projection' }));
    }
    current();
    if (!response.confirmed_context?.review_context || response.confirmed_context.session_id !== review.context.session_id) {
        throw new Error('Server review response was malformed; request a fresh review.');
    }
    review.context = response.confirmed_context;
    return response;
}

export async function cancelResolverReview(sessionId) {
    invalidateResolverOperation(sessionId);
    const review = reviews.get(sessionId);
    if (!review) throw Object.assign(new Error('Local review cleared. Server-side revocation could not be confirmed.'), { code: 'REVIEW_REVOCATION_UNCONFIRMED' });
    const options = scopedOptions(review, { action: 'cancel' });
    forget(review);
    try {
        const result = await request(`/api/review-contexts/${review.id}/action`, options);
        if (result.status !== 'revoked') throw new Error('Revocation acknowledgement was missing.');
    } catch (cause) {
        throw Object.assign(new Error('Local review cleared. Server-side revocation could not be confirmed.'),
            { code: 'REVIEW_REVOCATION_UNCONFIRMED', cause });
    }
}

export function runAadhaarPipeline({ message, confirmedContext, sessionId }) {
    const review = credentials(sessionId);
    return request('/api/orchestration/run', {
        method: 'POST',
        headers: scopedOptions(review).headers,
        body: JSON.stringify({
            user_request: {
                session_id: sessionId,
                user_message: message,
                domain: 'aadhaar',
            },
            confirmed_context: confirmedContext,
        }),
    });
}

export async function launchUidaiBrowser(confirmedContext, urn = "0000/12345/67890", openLivePortal = true) {
    const review = credentials(confirmedContext.session_id);
    const result = await request('/api/browser/launch-uidai', {
        method: 'POST',
        headers: scopedOptions(review).headers,
        body: JSON.stringify({
            confirmed_context: confirmedContext,
            urn,
            open_live_portal: openLivePortal,
        }),
    });
    review.executionState = { stage: result.current_stage, version: result.execution_state_version };
    return result;
}

export async function submitBrowserStep(sessionId, userConsent = true, notes = '', userInputs = {}) {
    const review = credentials(sessionId);
    if (review.executionUncertain) throw new Error('Execution is uncertain; human reconciliation is required.');
    if (!review.attempt) {
        if (!review.executionState || !Number.isInteger(review.executionState.version)) {
            throw new Error('Current server execution state is required.');
        }
        // Serialized once: transport retries cannot replace identity or citizen inputs.
        review.attempt = JSON.stringify({ session_id: review.context.session_id,
            request_id: globalThis.crypto.randomUUID(), expected_stage: review.executionState.stage,
            expected_state_version: review.executionState.version,
            user_consent: userConsent, notes, user_inputs: userInputs });
    }
    const result = await request('/api/browser/submit-step', {
        method: 'POST', headers: scopedOptions(review).headers, body: review.attempt,
    });
    if (result.execution_uncertain === true || (result.execution_result?.status === 'UNKNOWN' && result.retry_permitted !== true)) {
        review.executionUncertain = true;
    } else if (result.execution_result?.status === 'VERIFIED_SUCCESS' || result.retry_permitted === true) {
        if (!Number.isInteger(result.execution_state_version) || !result.current_stage) {
            throw new Error('Execution outcome lacks authoritative next state; attempt retained.');
        }
        review.executionState = { stage: result.current_stage, version: result.execution_state_version };
        review.attempt = null;
    }
    return result;
}

export function getBrowserSessionStatus(sessionId) {
    const review = credentials(sessionId);
    return request(`/api/browser/session-status/${review.context.session_id}`, scopedOptions(review));
}


export function getFinalReview(sessionId) {
    const review = credentials(sessionId);
    return request(`/api/browser/final-review/${encodeURIComponent(review.context.session_id)}`, scopedOptions(review));
}

export function finalReviewAction(sessionId, action, binding) {
    const review = credentials(sessionId);
    return request(`/api/browser/final-review/${encodeURIComponent(review.context.session_id)}`, {
        method: 'POST', headers: scopedOptions(review).headers,
        body: JSON.stringify({ action, binding }),
    });
}


// Read-only, opt-in backend diagnostic. Does not touch attempt identity or uncertainty.
export function inspectBrowserStructure(sessionId) {
    const review = credentials(sessionId);
    return request('/api/browser/inspect-structure', scopedOptions(review, {session_id:review.context.session_id}));
}
