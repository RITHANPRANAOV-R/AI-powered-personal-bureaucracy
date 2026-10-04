const API_BASE_URL = import.meta.env.VITE_API_URL || '';

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
    formData.append('document', file);
    return request('/api/documents/aadhaar/extract', {
        method: 'POST',
        body: formData,
    });
}

export function confirmAadhaarDocument(extraction, corrections = {}) {
    return request('/api/documents/aadhaar/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extraction, corrections }),
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
