const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function request(path, options) {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(payload.detail || payload.error || 'The assistant could not complete this step.');
    }
    return payload;
}

export function extractAadhaarDocument(file) {
    const formData = new FormData();
    formData.append('file', file);
    return request('/api/documents/aadhaar/extract', {
        method: 'POST',
        body: formData,
    });
}

export function confirmAadhaarDocument(extraction, corrections = {}, sessionId) {
    return request('/api/documents/aadhaar/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true, extraction, corrections, session_id: sessionId }),
    });
}

export function runAadhaarPipeline({ message, confirmedContext, sessionId }) {
    return request('/api/orchestration/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

export function launchUidaiBrowser(confirmedContext, urn = "0000/12345/67890", openLivePortal = true) {
    return request('/api/browser/launch-uidai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            confirmed_context: confirmedContext,
            urn,
            open_live_portal: openLivePortal,
        }),
    });
}

export function submitBrowserStep(sessionId, userConsent = true, notes = '') {
    return request('/api/browser/submit-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            user_consent: userConsent,
            notes,
        }),
    });
}

export function getBrowserSessionStatus(sessionId) {
    return request(`/api/browser/session-status/${sessionId}`);
}

