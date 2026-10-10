"""Temporary structural inspection: no portal actions, values, body text, or response contents."""
import asyncio
import ipaddress


def require_local_inspection(request, deadline, now):
    from fastapi import HTTPException
    if deadline is None:
        raise HTTPException(status_code=404, detail={"code": "PORTAL_DIAGNOSTIC_DISABLED", "message": "Structural inspection was not enabled at backend startup."})
    if now >= deadline:
        raise HTTPException(status_code=404, detail={"code": "PORTAL_DIAGNOSTIC_EXPIRED", "message": "The temporary structural inspection window has expired."})
    try:
        local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if (not local or request.headers.get("host") not in {"127.0.0.1:8000", "localhost:8000"}
            or request.headers.get("origin") != "http://localhost:5173"
            or any(name in request.headers for name in ("forwarded", "x-forwarded-for", "x-forwarded-host"))):
        raise HTTPException(status_code=403, detail="Structural inspection requires direct loopback access and the permitted frontend origin.")


# Filtering happens inside the renderer. Unrecognized text never reaches the backend.
STRUCTURE_SCRIPT = r"""() => {
    const words = new Set(('my aadhaar myaadhaar unique identification authority of india services address update online demographic demographics current new house building apartment flat number no street road lane landmark area locality sector care co pin pincode postal code village town city vtc post office state district resident document supporting upload manual select valid type proof by details to be updated review proceed next loading processing service home dashboard field form enter your').split(' '));
    const safeText = text => {
        const normalized = String(text || '').replace(/\s+/g, ' ').trim();
        if (!normalized) return null;
        if (normalized.length > 100) return '[redacted]';
        const tokens = normalized.toLowerCase().split(/[^a-z]+/).filter(Boolean);
        return tokens.length && !/[0-9@]/.test(normalized) && tokens.every(t => words.has(t)) ? normalized : '[redacted]';
    };
    const safeAttribute = text => {
        const normalized = String(text || '').trim();
        if (!normalized) return null;
        if (/^(?:mat-(?:input|select)|cdk)-(?:[0-9]{1,3})$/.test(normalized)) return normalized;
        const technical = normalized.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[_-]/g, ' ');
        return safeText(technical) !== '[redacted]' && /^[a-zA-Z_-]{1,64}$/.test(normalized) ? normalized : '[redacted]';
    };
    const visible = el => {
        const style = getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.visibility !== 'collapse' && el.getClientRects().length > 0;
    };
    const allowedOrigin = ['https://myaadhaar.uidai.gov.in', 'https://tathya.uidai.gov.in'].includes(location.origin);
    if (!allowedOrigin) return {origin:'[redacted]', path:'[redacted]', skipped:true};
    const routes = new Set(('dashboard home resident address address-update update-address updateaddress update aadhaar ssup demoupdate en_in demographic demographics document documents upload supporting-document supporting-documents review login access service services').split(' '));
    const path = '/' + location.pathname.split('/').filter(Boolean).map(s => routes.has(s.toLowerCase()) ? s : '[redacted]').join('/');
    const controls = [];
    let totalControls = 0;
    for (const el of document.querySelectorAll('input, select, textarea, [role="combobox"]')) {
        const type = String(el.getAttribute('type') || '').toLowerCase();
        const identity = [el.getAttribute('name'),el.getAttribute('id'),el.getAttribute('autocomplete')].join(' ').toLowerCase();
        if (['hidden','password'].includes(type) || /otp|captcha|aadhaar|one-time-code|password/.test(identity)) continue;
        totalControls++;
        if (controls.length >= 80) continue;
        controls.push({tag:el.tagName.toLowerCase(), id:safeAttribute(el.getAttribute('id')),
            name:safeAttribute(el.getAttribute('name')), formcontrolname:safeAttribute(el.getAttribute('formcontrolname')),
            role:safeText(el.getAttribute('role')), aria_label:safeText(el.getAttribute('aria-label')),
            label:safeText(el.labels ? Array.from(el.labels).map(l => l.textContent).join(' ') : ''),
            placeholder:safeText(el.getAttribute('placeholder')), visible:visible(el),
            enabled:!el.disabled && el.getAttribute('aria-disabled') !== 'true'});
    }
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,[role="heading"]')).filter(visible).slice(0,20)
        .map(el => ({tag:el.tagName.toLowerCase(), label:safeText(el.textContent)}));
    const loading = Array.from(document.querySelectorAll('[aria-busy="true"],[role="progressbar"],progress')).filter(visible).length;
    return {origin:location.origin, path, title:safeText(document.title), headings, controls,
        controls_truncated:totalControls>80, loading_indicator_count:loading, ready_state:document.readyState};
}"""


async def inspect_existing_session(manager, session_id):
    from fastapi import HTTPException
    from .interactive_session import page_observation_reference
    with manager._attempt_lock:
        session = manager._sessions.get(session_id)
        if session is None or session.page is None:
            raise HTTPException(status_code=409, detail="Existing browser page is unavailable; inspection cannot reconstruct a session.")
        if session.active_attempt is not None:
            raise HTTPException(status_code=409, detail="An execution attempt is active; wait before read-only inspection.")
        page, context, browser = session.page, session.page.context, session.browser
        stage, version = session.current_stage, session.execution_version
        page_reference = page_observation_reference(session)
        last_observation = dict(getattr(session, "last_observation", {}))
        if manager._check_authentication_continuity(session) is not None:
            raise HTTPException(status_code=409, detail="Browser continuity cannot be established.")
    async def capture():
        frames = list(page.frames)
        results = []
        for index, frame in enumerate(frames[:8]):
            results.append({"frame_index": index, **await frame.evaluate(STRUCTURE_SCRIPT)})
        return {"schema": "sanitized-portal-structure-v1", "stage": stage.value, "state_version": version,
                "page_reference": page_reference, "last_result_binding": last_observation,
                "frames": results, "frames_truncated": len(frames)>8}
    try:
        result = await asyncio.wait_for(capture(), timeout=10)
    except Exception:
        raise HTTPException(status_code=409, detail="Structural inspection failed or timed out; no portal action was performed.") from None
    with manager._attempt_lock:
        if (manager._sessions.get(session_id) is not session or session.page is not page
                or page.context is not context or session.browser is not browser
                or session.execution_version != version or session.current_stage != stage
                or session.active_attempt is not None or manager._check_authentication_continuity(session) is not None):
            raise HTTPException(status_code=409, detail="Session changed during inspection; snapshot discarded.")
    return result
