import { interpretExecutionStep } from './executionStepState';
import React, { useState, useRef } from 'react';
import {
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronLeft,
    CircleAlert,
    Copy,
    ExternalLink,
    FileCheck2,
    FileUp,
    Globe,
    KeyRound,
    LoaderCircle,
    LockKeyhole,
    Pencil,
    PlusCircle,
    ShieldAlert,
    ShieldCheck,
    Sparkles,
    Workflow,
} from 'lucide-react';
import {
    confirmAadhaarDocument,
    cancelResolverReview,
    invalidateResolverOperation,
    extractAadhaarDocument,
    launchUidaiBrowser,
    runAadhaarPipeline,
    submitBrowserStep,
    inspectBrowserStructure,
    getFinalReview,
    finalReviewAction,
} from './documentApi';

export function cleanLabelledAddressPin(address, confirmedPin) {
    const text = String(address || '');
    const pattern = /(?:pin\s*code|pincode|postal\s*code)\s*[:=-]\s*([1-9]\d{5})(?!\d)/gi;
    const labels = [...text.matchAll(pattern)];
    if (!labels.length) return text;
    if (confirmedPin && labels.some(match => match[1] !== confirmedPin)) {
        throw new Error('The PIN label in the new address conflicts with the confirmed PIN. Correct it before continuing.');
    }
    if (new Set(labels.map(match => match[1])).size !== 1) throw new Error('Multiple PIN labels require correction.');
    return text.replace(pattern, '').replace(/[ ,;\-]+$/, '').trim();
}

export function extractAddressRequest(request) {
    if (typeof request !== 'string' || !request.trim()) return {};
    const text = request.trim();
    const result = {};
    const capture = text.match(/(?:new\s+address\s*(?:is\s*)?[:=-]?|(?:update|change|modify)\s+(?:my\s+)?(?:aadhaar\s+)?address\s+(?:to|is|with)[:=-]?|shifted\s+to|moved\s+to|living\s+at|residing\s+at|address\s+(?:is|was|=|:))\s*([\s\S]+)/i);
    const legacy = text.match(/(?:aadhaar\s+address\s+(?:update|change)|change\s+aadhaar\s+address)\s*[-–—.]?\s*([\s\S]+)/i);
    let candidate = capture?.[1] || legacy?.[1];
    if (!candidate && !/check status/i.test(text) && text.length > 15 && !/^(?:i want to |please )?(?:update|change|modify)\s+(?:my\s+)?(?:aadhaar\s+)?address\s*$/i.test(text)) candidate = text;
    if (candidate) {
        candidate = candidate.replace(/^from\b.*?\bto\s+/i, '').replace(/(?:\.\s*|,\s*)(?:please\s+)?(?:update|change|modify)\b[\s\S]*$/i, '').trim();
        if (candidate.length >= 3) result.newAddress = candidate;
    }
    const pins = [...new Set((result.newAddress || text).match(/\b[1-9]\d{5}\b/g) || [])];
    if (pins.length > 1) throw new Error('Multiple PIN values in the proposed address require an explicit correction.');
    if (pins.length) result.pincode = pins[0];
    if (result.newAddress) result.newAddress = cleanLabelledAddressPin(result.newAddress, result.pincode);
    return result;
}

function Value({ value }) {
    if (value === null || value === undefined || value === '' || value === 'UNKNOWN') return <strong>UNKNOWN</strong>;
    if (Array.isArray(value)) return value.length ? <ul>{value.map((item, index) => <li key={index}><Value value={item} /></li>)}</ul> : <strong>UNKNOWN</strong>;
    if (typeof value === 'object' && Object.keys(value).length === 0) return <strong>UNKNOWN</strong>;
    if (typeof value === 'object') return <dl>{Object.entries(value).map(([key, item]) => <React.Fragment key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><Value value={item} /></dd></React.Fragment>)}</dl>;
    return <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{String(value)}</span>;
}

export function FinalReviewPanel({ review, busy, onApprove, onEdit, onCancel }) {
    if (!review?.package) return <section aria-label="Final review"><h3>FINAL REVIEW</h3><p>Submission information is UNKNOWN. Approval is unavailable.</p></section>;
    const blocked = review.state !== 'REVIEW_READY' || review.blocking_reasons?.length > 0;
    const groups = {
        Service: ['service'],
        Information: ['citizen_information', 'extracted_document_information', 'corrected_information', 'current_values', 'new_values', 'address', 'pincode'],
        Documents: ['supporting_documents', 'document_type', 'upload_validation'],
        Requirements: ['requirements', 'fees', 'submission_validation'],
        Declarations: ['declarations'],
        Warnings: ['warnings'],
    };
    return <section aria-label="Final review" className="details-card">
        <h3>FINAL REVIEW</h3><p>{review.state}</p>
        <p>Review every value before approval. This page does not submit your application.</p>
        {Object.entries(groups).map(([name, keys]) => <section key={name}><h4>{name}</h4>{keys.map(key => <div key={key}><strong>{key.replaceAll('_', ' ')}</strong><Value value={review.package[key]} /></div>)}</section>)}
        <p>UNKNOWN fields: {(review.unknown_fields || []).join(', ') || 'None'}</p>
        <ul>{(review.blocking_reasons || []).map(reason => <li key={reason}>{reason}</li>)}</ul>
        <p>Approval expires after 15 minutes and permits one attempt. Changes require review and approval again.</p>
        <button type="button" disabled={busy} onClick={onEdit}>Edit / Correct</button>
        <button type="button" disabled={busy || blocked} onClick={() => onApprove(review.binding)}>Approve &amp; Submit</button>
        <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
    </section>;
}

export function projectedAddressInputs(context) {
    // Do not manufacture quick corrections that invalidate a reviewed projection.
    const facts = context.facts;
    const read = (...keys) => keys.map(key => facts[key]?.value).find(value => typeof value === 'string' && value.trim()) || '';
    return {
        new_address: cleanLabelledAddressPin(read('new_address'), read('pincode')),
        pincode: read('pincode'), house_no: read('house_no', 'house', 'building', 'flat'),
        street: read('street', 'road', 'lane'), locality: read('locality', 'area', 'sector'),
        landmark: read('landmark'), care_of: read('care_of'),
    };
}

export function resolverRequestOptions(action, review) {
    if (action === 'resolve') return { resolve_address: true };
    if (action === 'continue_without_projection') return {};
    if (action !== 'confirm_post_office') throw new Error('Explicit Post Office confirmation is required.');
    const result = review?.confirmed_data?.address_resolution;
    if (review?.resolver_projection?.eligible !== true || result?.status !== 'resolved'
            || result.conflicts?.length || result.post_office?.status !== 'resolved') {
        throw new Error('Resolve and review an eligible, unambiguous Post Office before explicitly confirming projection.');
    }
    if (!review.review_reference) throw new Error('Server-published review reference is required.');
    return { review_reference: review.review_reference, confirm_resolver_projection: true };
}

export function ResolverReviewPanel({ review, busy, onResolve, onConfirm, onCancel }) {
    const resolution = review?.confirmed_data?.address_resolution;
    return <section aria-label="Post Office options" className="details-card">
        <h3>Check Post Office (optional)</h3>
        <p>Look up Post Office options for your new PIN. Nothing changes unless you explicitly confirm a suitable option. This does not approve final submission.</p>
        <button type="button" disabled={busy} onClick={onResolve}>Look up Post Office options</button>
        {review && <>
            <p>Lookup status: {resolution?.status || 'UNKNOWN'}</p>
            <p>No candidate is selected automatically. Check the PIN, candidates, conflicts and source evidence.</p>
            <Value value={resolution} />
            {!review.resolver_projection?.eligible && <p role="alert">{review.resolver_projection?.reason || 'No suitable Post Office is available. Check the new PIN or continue without selecting a Post Office.'}</p>}
            <p>Post Office option to confirm: {review.resolver_projection?.post_office || 'UNKNOWN'}</p>
            <button type="button" disabled={busy || review.resolver_projection?.eligible !== true}
                onClick={onConfirm}>Use this Post Office &amp; continue</button>
        </>}
        {(review || busy) && <button type="button" onClick={onCancel}>Cancel Post Office lookup</button>}
    </section>;
}

const steps = [
    { label: 'Your request', short: 'Request' },
    { label: 'Your document', short: 'Upload' },
    { label: 'Review details', short: 'Review' },
    { label: 'Next steps', short: 'Result' },
];

const standardFields = [
    ['name', 'Full Name'],
    ['aadhaar_number', '12-Digit Aadhaar Number'],
    ['date_of_birth', 'Date of Birth'],
    ['gender', 'Gender'],
    ['masked_aadhaar', 'Masked Reference / VID'],
    ['existing_address', 'Current Address'],
    ['new_address', 'New Address (to update)'],
    ['pincode', 'PIN Code'],
];

const sessionId = `aadhaar-session-${Math.random().toString(36).slice(2, 9)}`;

function fieldValue(data, key) {
    const field = data?.[key];
    return typeof field === 'object' ? field?.value : field;
}

export function ReviewDetails({ data, corrections = {}, onCorrect, busy, addressOnly = false,
    review, includePostOffice = false, onPostOfficeChoice }) {
    const fields = addressOnly ? standardFields.filter(([key]) => ['existing_address', 'new_address', 'pincode'].includes(key)) : standardFields;
    const eligible = review?.resolver_projection?.eligible === true;
    const office = eligible ? review.resolver_projection.post_office : null;
    return <div className="details-card" aria-label="Review your details">
        {fields.map(([key, label]) => {
            const value = corrections[key] || fieldValue(data, key);
            return <div className="detail-row" key={key}>
                <span>{label}</span>
                <strong className={!value ? 'detail-missing' : undefined}>{value || (key === 'new_address' ? 'Click "Fill" to add new address' : 'Click "Fill" to add this detail')}</strong>
                <div className="detail-actions">
                    {corrections[key] && <em>updated</em>}
                    <button type="button" className="text-button detail-edit" disabled={busy}
                        aria-label={`${value ? 'Change' : 'Fill'} ${label}`} onClick={() => onCorrect(key)}>
                        {value ? <Pencil size={12} /> : <PlusCircle size={12} />}{value ? 'Change' : 'Fill'}
                    </button>
                </div>
            </div>;
        })}
        {office && <div className="detail-row">
            <span>Post Office</span><strong>{office}</strong>
            <label className="post-office-choice"><input type="checkbox" checked={includePostOffice} disabled={busy}
                onChange={(event) => onPostOfficeChoice(event.target.checked)} />Use this Post Office</label>
        </div>}
        {review && !eligible && ['ambiguous', 'conflict'].includes(review.confirmed_data?.address_resolution?.status) &&
            <div className="detail-row"><span>Post Office</span><strong>No option selected</strong><span>Check the address or choose on the official form.</span></div>}
    </div>;
}

export function AddressReview(props) {
    return ReviewDetails({ ...props, addressOnly: true });
}

export function canCheckPostOffice(extracted, edits = {}) {
    const data = extracted?.data;
    if (!data) return false;
    const value = (key) => edits[key] || fieldValue(data, key) || '';
    return ['name', 'date_of_birth', 'existing_address', 'new_address'].every((key) => String(value(key)).trim())
        && /^[1-9]\d{5}$/.test(value('pincode'))
        && [...Object.keys(extracted.conflicts || {}), ...Object.keys(extracted.validation_errors || {})].every((key) => edits[key]);
}

function resultTone(status = '') {
    const value = status.toLowerCase();
    if (value.includes('completed')) return 'success';
    if (value.includes('blocked') || value.includes('failed')) return 'danger';
    if (value.includes('human') || value.includes('pending') || value.includes('clarif')) return 'warning';
    return 'info';
}

function TemporaryPortalInspection({ sessionId, operation, submitting }) {
    const [snapshot, setSnapshot] = useState(null);
    const [busy, setBusy] = useState(false);
    async function inspect() {
        if (busy || submitting) return;
        const revision = operation.current;
        setBusy(true);
        setSnapshot(null);
        try {
            const data = await inspectBrowserStructure(sessionId);
            if (revision === operation.current) setSnapshot({revision, data});
        } catch (err) {
            const explanations = {
                404: 'Diagnostic unavailable: the endpoint is not loaded, disabled, or expired.',
                403: 'Diagnostic denied: origin or session authorization was rejected.',
                401: 'Diagnostic denied: session authorization is required.',
                409: 'Diagnostic unavailable: the existing session is busy, changed, or cannot be inspected safely.',
            };
            const diagnosticReasons = {
                PORTAL_DIAGNOSTIC_DISABLED: 'Diagnostic disabled at backend startup. Enabling it requires an agreed controlled restart; the current session has not been changed.',
                PORTAL_DIAGNOSTIC_EXPIRED: 'The temporary diagnostic window expired. Do not repeat portal actions; agree on controlled recovery before restarting.',
            };
            if (revision === operation.current) setSnapshot({revision, data:{
                status: diagnosticReasons[err?.code] || explanations[err?.status] || 'Diagnostic unavailable: no structural capture was obtained.',
                http_status: Number.isInteger(err?.status) ? err.status : null,
            }});
        } finally { setBusy(false); }
    }
    return <section aria-label="Temporary portal inspection">
        <button className="secondary-button" onClick={inspect} disabled={submitting || busy}>
            {busy ? 'Inspecting structure…' : 'Inspect page structure (read-only)'}
        </button>
        <p>This diagnostic does not retry actions or clear uncertainty. Unrecognized text is redacted.</p>
        {snapshot?.revision === operation.current && <pre>{JSON.stringify(snapshot.data, null, 2)}</pre>}
    </section>;
}

export default function AadhaarAssistant() {
    const [step, setStep] = useState(0);
    const [request, setRequest] = useState('I want to update my Aadhaar address');
    const [file, setFile] = useState(null);
    const [extraction, setExtraction] = useState(null);
    const [confirmedContext, setConfirmedContext] = useState(null);
    const [corrections, setCorrections] = useState({});
    const [correcting, setCorrecting] = useState(false);
    const [correctionField, setCorrectionField] = useState('new_address');
    const [correctionValue, setCorrectionValue] = useState('');
    const [status, setStatus] = useState('idle');
    const [error, setError] = useState('');
    const [copiedNotification, setCopiedNotification] = useState('');
    const [result, setResult] = useState(null);

    // Interactive Browser Session States
    const [browserSessionActive, setBrowserSessionActive] = useState(false);
    const [currentStageData, setCurrentStageData] = useState(null);
    const [completedStages, setCompletedStages] = useState([]);
    const [sessionUrn, setSessionUrn] = useState('');
    const [isSessionCompleted, setIsSessionCompleted] = useState(false);
    const [submittingStep, setSubmittingStep] = useState(false);
    const [finalReview, setFinalReview] = useState(null);
    const [launchingBrowser, setLaunchingBrowser] = useState(false);
    const [stepAddressInputs, setStepAddressInputs] = useState({
        new_address: '',
        pincode: '',
        house_no: '',
        street: '',
        landmark: '',
        locality: '',
        care_of: '',
    });

    const [includePostOffice, setIncludePostOffice] = useState(false);
    const [resolverReview, setResolverReview] = useState(null);
    // Keep inspection reachable without reloading and losing the in-memory capability.
    // The backend independently enforces opt-in, expiry, origin and session authorization.
    const inspectionEnabled = globalThis.location?.origin === 'http://localhost:5173';

    const executionOperation = useRef(0);
    const reviewOperation = useRef(0);
    function invalidateReview() {
        reviewOperation.current += 1;
        invalidateResolverOperation(sessionId);
        setResolverReview(null);
        setIncludePostOffice(false);
    }
    const extractionData = extraction?.data;

    async function handleFile(fileToRead) {
        if (!fileToRead) return;
        invalidateReview();
        const operation = reviewOperation.current;
        setFile(fileToRead);
        setError('');
        setStatus('extracting');
        setStep(2);

        try {
            const response = await extractAadhaarDocument(fileToRead, extractAddressRequest(request));
            if (operation !== reviewOperation.current) return;
            if (response.status && !['success', 'missing_required_fields'].includes(response.status)) {
                throw new Error(response.error || 'Some details could not be read reliably.');
            }
            setExtraction(response);
            if (response.status === 'missing_required_fields') setError((response.warnings || []).join(' ' ) || 'Correct missing or conflicting fields before confirmation.');
            setStatus('idle');
            if (canCheckPostOffice(response, corrections)) void requestResolution(response, corrections);
        } catch (requestError) {
            if (operation !== reviewOperation.current || requestError.code === 'STALE_REVIEW_OPERATION') return;
            if (requestError.code === 'REVIEW_CAPABILITY_AUTH_FAILED') invalidateReview();
            setStatus('error');
            setError(requestError.message);
        }
    }

    async function cancelProjectionReview() {
        invalidateReview();
        const operation = reviewOperation.current;
        setStatus('confirming');
        try { await cancelResolverReview(sessionId); if (operation === reviewOperation.current) setStatus('idle'); }
        catch (requestError) {
            if (operation !== reviewOperation.current) return;
            setError(requestError.message); setStatus('error');
        }
    }

    async function requestResolution(inputExtraction = extraction, inputCorrections = corrections) {
        if (isBusy) return;
        setStatus('confirming');
        setError('');
        invalidateReview();
        const operation = reviewOperation.current;
        try {
            const response = await confirmAadhaarDocument(inputExtraction, inputCorrections, sessionId,
                resolverRequestOptions('resolve'));
            if (operation !== reviewOperation.current) return;
            setResolverReview(response);
            setStatus('idle');
        } catch (requestError) {
            if (operation !== reviewOperation.current || requestError.code === 'STALE_REVIEW_OPERATION') return;
            if (requestError.code === 'REVIEW_CAPABILITY_AUTH_FAILED') {
                invalidateReview();
                setStatus('error');
                setError('Your review session could not be verified. Confirm your details again.');
            } else if (requestError.status === 400 || requestError.status === 422 || requestError.status === 403) {
                setStatus('error');
                setError(requestError.message);
            } else {
                setStatus('idle');
                setError('Post Office options could not be checked. Your address and PIN are unchanged; you can confirm your details without selecting a Post Office.');
            }
        }
    }

    async function confirmDetails(action = 'continue_without_projection') {
        if (isBusy) return;
        const operation = ++reviewOperation.current;
        setStatus('confirming');
        setError('');
        try {
            const options = resolverRequestOptions(action, resolverReview);
            const response = await confirmAadhaarDocument(extraction, corrections, sessionId, options);
            if (operation !== reviewOperation.current) return;
            const ctx = response.confirmed_context || response;
            setConfirmedContext(ctx);
            setStatus('idle');
            setStep(3);
            // Automatically initiate interactive session on confirmation
            if (browserSessionActive) setStepAddressInputs(projectedAddressInputs(ctx));
            else await startInteractiveSession(ctx);
        } catch (requestError) {
            if (operation !== reviewOperation.current || requestError.code === 'STALE_REVIEW_OPERATION') return;
            if (requestError.code === 'REVIEW_CAPABILITY_AUTH_FAILED') invalidateReview();
            setStatus('error');
            setError(requestError.message);
        }
    }

    function confirmReviewedDetails() {
        return confirmDetails(includePostOffice ? 'confirm_post_office' : 'continue_without_projection');
    }

    async function startInteractiveSession(ctx) {
        executionOperation.current += 1;
        setLaunchingBrowser(true);
        setError('');
        try {
            const extractedAadhaar = fieldValue(extractionData, 'aadhaar_number') || fieldValue(extractionData, 'masked_aadhaar') || '';
            const aadhaarVal = corrections.aadhaar_number || corrections.masked_aadhaar || extractedAadhaar || '999912345678';
            const addrVal = corrections.new_address || fieldValue(extractionData, 'new_address') || corrections.existing_address || fieldValue(extractionData, 'existing_address') || '';
            const pinVal = corrections.pincode || fieldValue(extractionData, 'pincode') || '';

            setStepAddressInputs((prev) => ctx?.facts
                ? projectedAddressInputs(ctx) : ({
                ...prev,
                new_address: addrVal,
                pincode: pinVal,
                house_no: prev.house_no || '',
                street: prev.street || '',
                locality: prev.locality || '',
            }));

            const contextToUse = ctx || confirmedContext || {
                session_id: sessionId,
                facts: {
                    name: { value: corrections.name || fieldValue(extractionData, 'name') || 'Citizen', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    aadhaar_number: { value: aadhaarVal, provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    existing_address: { value: corrections.existing_address || fieldValue(extractionData, 'existing_address') || '', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    new_address: { value: addrVal, provenance: 'user-input', status: 'confirmed', allowed_for_execution: true },
                    pincode: { value: pinVal, provenance: 'user-input', status: 'confirmed', allowed_for_execution: true },
                    date_of_birth: { value: corrections.date_of_birth || fieldValue(extractionData, 'date_of_birth') || '', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    gender: { value: corrections.gender || fieldValue(extractionData, 'gender') || 'Male', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    masked_aadhaar: { value: corrections.masked_aadhaar || fieldValue(extractionData, 'masked_aadhaar') || aadhaarVal, provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                },
                document_refs: file ? [file.name] : ['Uploaded_Aadhaar_Document.pdf'],
            };

            const sessionResponse = await launchUidaiBrowser(contextToUse, "", true);
            setBrowserSessionActive(true);
            setCurrentStageData(sessionResponse.stage_info);
            setSessionUrn('');
        } catch (err) {
            setError(`Could not start browser session: ${err.message}`);
        } finally {
            setLaunchingBrowser(false);
        }
    }

    async function openFinalReview() {
        setError('');
        try {
            const response = await getFinalReview(sessionId);
            setFinalReview(response.final_review || null);
            if (!response.final_review) setError(response.execution_result?.message || 'Final review is unavailable.');
        } catch (err) { setError(err.message); }
    }

    async function handleFinalReviewAction(action, binding) {
        if (submittingStep) return;
        setSubmittingStep(true);
        try {
            const response = await finalReviewAction(sessionId, action, binding);
            if (action === 'Edit / Correct') {
                setFinalReview(null); setStep(2); setCorrecting(true);
                setConfirmedContext(null);
            } else if (action === 'Cancel') {
                setFinalReview(null);
            } else {
                const outcome = interpretExecutionStep(response, 'stage_5_review');
                if (outcome.final) {
                    setIsSessionCompleted(true); setCurrentStageData(null); setSessionUrn(response.urn);
                } else {
                    setError(`${outcome.status}: ${outcome.message}`);
                    const refreshed = await getFinalReview(sessionId);
                    setFinalReview(refreshed.final_review || null);
                }
            }
        } catch (err) { setError(err.message); }
        finally { setSubmittingStep(false); }
    }

    async function handleAppSubmitStep() {
        if (!browserSessionActive || submittingStep || !currentStageData) return;
        if (currentStageData.id === 'stage_5_review') { await openFinalReview(); return; }
        const operation = ++executionOperation.current;
        const submittedStage = currentStageData.id;
        setSubmittingStep(true);
        setError('');
        try {
            if (submittedStage === 'stage_3_address' && (!stepAddressInputs.house_no.trim() || !stepAddressInputs.street.trim())) {
                setError('Confirm House / Building and Street / Road in the fields above. A combined address alone cannot determine these fields safely.');
                return;
            }
            const stepResult = await submitBrowserStep(sessionId, true, '', stepAddressInputs);
            if (operation !== executionOperation.current) return;
            const outcome = interpretExecutionStep(stepResult, submittedStage);
            if (!outcome.completed) {
                const diagnostic = stepResult.execution_diagnostic;
                const stageLabel = {stage_1a_otp: 'OTP checkpoint', stage_1b_login: 'dashboard',
                    stage_2_service: 'address form', stage_3_address: 'document page', stage_4_document: 'document acceptance'}[diagnostic?.stage_verifier];
                const actualCheck = {address_destination:'address destination', address_form_readiness:'address form readiness',
                    address_values:'address readback', document_destination:'document page'}[diagnostic?.verification_check] || stageLabel;
                const marker = diagnostic?.verifier_version === 'services-dashboard-v2'
                    && ['new_attempt', 'retained', 'none'].includes(diagnostic.result_origin)
                    ? ` [services-dashboard-v2; ${diagnostic.result_origin}; verifier ${diagnostic.verifier_invoked === true ? 'invoked' : 'not invoked'}${actualCheck ? `; checking ${actualCheck}` : ''}]`
                    : ' [runtime diagnostic unavailable]';
                setError(`${outcome.status}: ${outcome.message}${marker}`);
                return;
            }
            setCompletedStages((prev) => prev.some((stage) => stage.id === currentStageData.id)
                ? prev : [...prev, currentStageData]);
            if (outcome.final) {
                setIsSessionCompleted(true);
                setCurrentStageData(null);
                setSessionUrn(stepResult.urn);
            } else {
                setCurrentStageData(stepResult.stage_info);

            }
        } catch (err) {
            if (operation === executionOperation.current) setError(`Step submission failed: ${err.message}`);
        } finally {
            if (operation === executionOperation.current) setSubmittingStep(false);
        }
    }

    async function continueToPipeline(customContext = null) {
        setStatus('processing');
        setError('');
        const ctxToUse = customContext || confirmedContext;
        try {
            const response = await runAadhaarPipeline({
                message: request,
                confirmedContext: ctxToUse,
                sessionId,
            });
            setResult(response);
            setStatus('idle');
        } catch (requestError) {
            setStatus('error');
            setError(requestError.message);
        }
    }

    function saveCorrection() {
        if (isBusy || !correctionValue.trim()) return;
        invalidateReview(); // Corrections invalidate the published result and citizen choice.
        const edits = { ...corrections, [correctionField]: correctionValue.trim() };
        setCorrections(edits);
        setCorrecting(false);
        setCorrectionValue('');
        if (canCheckPostOffice(extraction, edits)) void requestResolution(extraction, edits);
    }

    function copyDemographics() {
        const name = corrections.name || fieldValue(extractionData, 'name') || '';
        const dob = corrections.date_of_birth || fieldValue(extractionData, 'date_of_birth') || '';
        const gender = corrections.gender || fieldValue(extractionData, 'gender') || '';
        const existingAddr = corrections.existing_address || fieldValue(extractionData, 'existing_address') || '';
        const newAddr = corrections.new_address || '';
        const pin = corrections.pincode || '';

        const text = [
            `Name: ${name}`,
            `Date of Birth: ${dob}`,
            `Gender: ${gender}`,
            `Current Address: ${existingAddr}`,
            newAddr ? `New Address: ${newAddr}` : '',
            pin ? `PIN Code: ${pin}` : '',
        ].filter(Boolean).join('\n');

        navigator.clipboard.writeText(text);
        setCopiedNotification('Demographics copied to clipboard!');
        setTimeout(() => setCopiedNotification(''), 3000);
    }

    const isBusy = ['extracting', 'confirming', 'processing'].includes(status) || submittingStep || launchingBrowser;
    const resultStatus = result?.status || result?.integration_result?.status || '';

    // Check for missing data
    const currentAddressVal = corrections.existing_address || fieldValue(extractionData, 'existing_address') || '';
    const currentNameVal = corrections.name || fieldValue(extractionData, 'name') || '';
    const isAddressMissing = !currentAddressVal.trim();
    const isNameMissing = !currentNameVal.trim();
    const hasMissingCriticalData = isAddressMissing || isNameMissing;

    return (
        <div className="assistant-shell">
            <header className="topbar">
                <div className="brand-lockup">
                    <div className="brand-mark"><Sparkles size={19} /></div>
                    <div>
                        <div className="brand-name">Aadhaar<span>care</span></div>
                        <div className="brand-caption">Interactive Bureaucracy Copilot</div>
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <button
                        className="secondary-button"
                        style={{ height: '34px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '5px' }}
                        onClick={() => startInteractiveSession()}
                        disabled={launchingBrowser}
                    >
                        <Globe size={14} /> {launchingBrowser ? 'Opening...' : 'Open Official UIDAI'}
                    </button>
                    <div className="privacy-note"><LockKeyhole size={14} /> Your document stays private</div>
                </div>
            </header>

            <main className="workspace">
                <aside className="intro-rail">
                    <div className="eyebrow">PERSONAL BUREAUCRACY <span>01</span></div>
                    <h1>One small step at a time.</h1>
                    <p className="intro-copy">We’ll help you prepare an Aadhaar address update, collect any missing information in-app, and guide every page submission on the official portal.</p>
                    <div className="rail-note">
                        <ShieldCheck size={18} />
                        <span>All page submissions require your explicit consent in this app.</span>
                    </div>
                    <div className="rail-orbit orbit-one" />
                    <div className="rail-orbit orbit-two" />
                </aside>

                <section className="flow-panel">
                    <nav className="stepper" aria-label="Aadhaar update progress">
                        {steps.map((item, index) => (
                            <div className={`step-item ${index === step ? 'active' : ''} ${index < step ? 'complete' : ''}`} key={item.label}>
                                <span className="step-number">{index < step ? <Check size={14} /> : `0${index + 1}`}</span>
                                <span className="step-label">{item.label}</span>
                                {index < steps.length - 1 && <span className="step-line" />}
                            </div>
                        ))}
                    </nav>

                    {step === 0 && (
                        <section className="flow-view appear">
                            <div className="section-kicker">Let’s get started</div>
                            <h2>What would you like to do?</h2>
                            <p className="section-lede">Tell us in your own words. We’ll ask only for what this request needs.</p>
                            <label className="field-label" htmlFor="request">Your request</label>
                            <textarea id="request" className="request-box" value={request} onChange={(event) => setRequest(event.target.value)} rows="3" />
                            <div className="suggestion-row">
                                <button className="suggestion active" onClick={() => setRequest('I want to update my Aadhaar address')}>Update address <ArrowRight size={15} /></button>
                                <button className="suggestion" onClick={() => setRequest('I want to check my Aadhaar status')}>Check status</button>
                            </div>
                            <div className="action-row">
                                <button className="primary-button" disabled={!request.trim()} onClick={() => setStep(1)}>
                                    Continue <ArrowRight size={17} />
                                </button>
                                <button
                                    className="secondary-button"
                                    onClick={() => startInteractiveSession()}
                                    disabled={launchingBrowser}
                                    title="Open official myAadhaar portal in Chromium now"
                                >
                                    <Globe size={15} /> Open Official UIDAI Portal
                                </button>
                            </div>
                        </section>
                    )}

                    {step === 1 && (
                        <section className="flow-view appear">
                            <button className="back-button" onClick={() => setStep(0)}><ChevronLeft size={16} /> Back</button>
                            <div className="section-kicker">Step two</div>
                            <h2>Bring your existing Aadhaar</h2>
                            <p className="section-lede">Upload a clear PDF or image. We’ll read only the details needed for your request.</p>
                            <label className="upload-zone" htmlFor="aadhaar-file">
                                <span className="upload-icon"><FileUp size={24} /></span>
                                <strong>{file ? file.name : 'Choose an Aadhaar PDF or image'}</strong>
                                <span>PDF, PNG, JPG or JPEG · up to 25 MB</span>
                                <input id="aadhaar-file" type="file" accept=".pdf,.png,.jpg,.jpeg,image/*,application/pdf" onChange={(event) => handleFile(event.target.files?.[0])} />
                            </label>
                            <div className="quiet-notice"><LockKeyhole size={16} /><span>Your file is used for this review only. Full security controls apply.</span></div>
                        </section>
                    )}

                    {step === 2 && (
                        <section className="flow-view appear">
                            <button className="back-button" disabled={isBusy} onClick={() => setStep(1)}><ChevronLeft size={16} /> Back</button>
                            {status === 'extracting' ? (
                                <div className="loading-state"><div className="loader-ring"><LoaderCircle size={30} /></div><div className="section-kicker">Just a moment</div><h2>Reading your document...</h2><p className="section-lede">We’re looking for the details needed to prepare your update.</p></div>
                            ) : extractionData ? (
                                <>
                                    <div className="section-kicker">Check & Complete Details</div>
                                    <h2>Do these details look right?</h2>
                                    <p className="section-lede">These details were extracted from your document. If any information is missing or you want to update your new address, add it below.</p>

                                    {hasMissingCriticalData && (
                                        <div className="correction-panel" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.3)', marginBottom: '1rem', width: '100%' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', fontWeight: 'bold', fontSize: '12px' }}>
                                                <ShieldAlert size={16} /> Missing information detected
                                            </div>
                                            <p style={{ fontSize: '11px', color: '#cbd5e1', margin: '4px 0 10px' }}>
                                                Please fill in the missing address or details below so your UIDAI update is accurate.
                                            </p>
                                        </div>
                                    )}

                                    <ReviewDetails data={extractionData} corrections={corrections} busy={isBusy}
                                        review={resolverReview} includePostOffice={includePostOffice} onPostOfficeChoice={setIncludePostOffice}
                                        onCorrect={(key) => { setCorrectionField(key); setCorrectionValue(corrections[key] || fieldValue(extractionData, key) || ''); setCorrecting(true); }} />

                                    {correcting && (
                                        <div className="correction-panel">
                                            <div className="field-label">Add or Update Detail</div>
                                            <div className="correction-row">
                                                <select value={correctionField} onChange={(event) => setCorrectionField(event.target.value)}>
                                                    {standardFields.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                                </select>
                                                <input
                                                    autoFocus
                                                    value={correctionValue}
                                                    onChange={(event) => setCorrectionValue(event.target.value)}
                                                    placeholder={`Enter ${standardFields.find(f => f[0] === correctionField)?.[1] || 'value'}`}
                                                />
                                            </div>
                                            <button className="text-button" onClick={saveCorrection}>Save value</button>
                                        </div>
                                    )}

                                    <div className="action-row">
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <button className="secondary-button" onClick={() => setCorrecting(true)}>
                                                <Pencil size={16} /> Edit or Add Field
                                            </button>
                                            <button className="secondary-button" onClick={copyDemographics}>
                                                <Copy size={16} /> Copy Details
                                            </button>
                                        </div>
                                        <button className="primary-button" onClick={confirmReviewedDetails} disabled={isBusy}>
                                            <CheckCircle2 size={17} /> Confirm details
                                        </button>
                                    </div>
                                    {copiedNotification && <div style={{ fontSize: '11px', color: '#10b981', marginTop: '6px' }}>✓ {copiedNotification}</div>}
                                </>
                            ) : <ErrorState message={error || 'We could not read this document.'} onRetry={() => setStep(1)} />}
                        </section>
                    )}

                    {step === 3 && (
                        <section className="flow-view appear">
                            <div className="section-kicker">Step four · Official Portal Copilot</div>
                            <h2>Interactive Submission Control</h2>
                            <p className="section-lede">The official UIDAI portal is open in Chromium. Review each stage and submit using the buttons below.</p>

                            {/* Completed Stages History */}
                            {completedStages.length > 0 && (
                                <div className="details-card" style={{ marginBottom: '1rem', borderLeft: '4px solid #10b981' }}>
                                    <div className="field-label" style={{ padding: '8px 15px', fontWeight: 600, color: '#10b981' }}>Completed Steps</div>
                                    {completedStages.map((st, i) => (
                                        <div key={i} className="detail-row" style={{ minHeight: '38px', fontSize: '12px' }}>
                                            <span style={{ color: '#10b981', fontWeight: 'bold' }}>✓ Step 0{st.step_number}</span>
                                            <span>{st.title}</span>
                                            <em style={{ color: '#10b981' }}>submitted</em>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Active Stage Consent Box */}
                            {currentStageData && !isSessionCompleted && (
                                <div className="correction-panel" style={{ width: '100%', background: 'rgba(14,165,233,0.08)', border: '1.5px solid #0284c7', padding: '1.25rem', borderRadius: '12px', marginBottom: '1.25rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 'bold', fontSize: '14px' }}>
                                            <Workflow size={18} /> Step 0{currentStageData.step_number}: {currentStageData.title}
                                        </div>
                                        <span style={{ fontSize: '10px', background: '#0284c7', color: 'white', padding: '2px 8px', borderRadius: '999px', fontWeight: 'bold' }}>
                                            Awaiting Your Submit
                                        </span>
                                    </div>

                                    <p style={{ fontSize: '12px', color: '#e2e8f0', margin: '0.5rem 0', lineHeight: 1.5 }}>
                                        {currentStageData.description}
                                    </p>

                                    {currentStageData.requires_portal_interaction && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#fbbf24', background: 'rgba(245,158,11,0.1)', padding: '8px 10px', borderRadius: '6px', margin: '8px 0 12px' }}>
                                            <KeyRound size={15} /> <strong>UIDAI Security Notice:</strong> Enter CAPTCHA and Mobile OTP in the Chromium window, then click submit below.
                                        </div>
                                    )}

                                    {currentStageData.id === 'stage_3_address' && (
                                        <div style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '12px', margin: '12px 0' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: '#38bdf8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                <Sparkles size={14} /> Demographic Address Fields to Prepopulate & Submit:
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px' }}>
                                                <div>
                                                    <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>House / Flat / Building No</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.house_no}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, house_no: e.target.value }))}
                                                        placeholder="e.g. Flat 402, Lotus Apts"
                                                        style={{ width: '100%', padding: '6px 8px', fontSize: '12px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
                                                    />
                                                </div>
                                                <div>
                                                    <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>Street / Road / Lane</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.street}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, street: e.target.value }))}
                                                        placeholder="e.g. 12th Main Road"
                                                        style={{ width: '100%', padding: '6px 8px', fontSize: '12px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
                                                    />
                                                </div>
                                                <div>
                                                    <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>Area / Locality / Sector</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.locality}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, locality: e.target.value }))}
                                                        placeholder="e.g. Koramangala 4th Block"
                                                        style={{ width: '100%', padding: '6px 8px', fontSize: '12px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
                                                    />
                                                </div>
                                                <div>
                                                    <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>PIN Code</label>
                                                    <input
                                                        type="text"
                                                        maxLength={6}
                                                        value={stepAddressInputs.pincode}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, pincode: e.target.value }))}
                                                        placeholder="6-digit PIN"
                                                        style={{ width: '100%', padding: '6px 8px', fontSize: '12px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
                                                    />
                                                </div>
                                                <div style={{ gridColumn: '1 / -1' }}>
                                                    <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>Full New Address (Combined)</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.new_address}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, new_address: e.target.value }))}
                                                        placeholder="Full combined new address..."
                                                        style={{ width: '100%', padding: '6px 8px', fontSize: '12px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
                                                    />
                                                </div>
                                            </div>
                                            {(!stepAddressInputs.house_no || !stepAddressInputs.street) && (
                                                <p role="status">Confirm House / Building and Street / Road above before filling the portal. A combined address does not determine these fields safely. Enter Area / Locality only if you can confirm it; city and locality are not automatically interchangeable.</p>
                                            )}
                                            {(!stepAddressInputs.new_address && !stepAddressInputs.house_no) && (
                                                <div style={{ fontSize: '11px', color: '#f59e0b', marginTop: '6px' }}>
                                                    ⚠️ Missing detail detected: Please enter your House No or New Address above before clicking submit.
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {finalReview && <FinalReviewPanel review={finalReview} busy={submittingStep}
                                        onApprove={(binding) => handleFinalReviewAction('Approve & Submit', binding)}
                                        onEdit={() => handleFinalReviewAction('Edit / Correct')}
                                        onCancel={() => handleFinalReviewAction('Cancel')} />}
                                    {currentStageData.id === 'stage_4_document' && !finalReview &&
                                        <button type="button" onClick={openFinalReview}>Review submission package</button>}
                                    {!finalReview && <div style={{ marginTop: '1rem' }}>
                                        <button
                                            className="primary-button"
                                            style={{ width: '100%', minHeight: '44px', fontSize: '13px', background: 'linear-gradient(110deg, #0284c7, #0ea5e9)', color: '#fff', borderColor: '#0284c7', boxShadow: '0 4px 14px rgba(2,132,199,0.3)' }}
                                            onClick={handleAppSubmitStep}
                                            disabled={submittingStep}
                                        >
                                            {submittingStep ? <><LoaderCircle size={16} className="loader-ring" /> Submitting Step...</> : <><CheckCircle2 size={16} /> {currentStageData.id === 'stage_5_review' ? 'Open Final Review' : currentStageData.button_label}</>}
                                        </button>
                                    </div>}
                                </div>
                            )}

                            {/* Final Completed View */}
                            {isSessionCompleted && (
                                <div className="details-card" style={{ width: '100%', borderLeft: '4px solid #16a34a', padding: '1.25rem', background: 'rgba(22,163,74,0.08)', marginBottom: '1.25rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#16a34a', fontWeight: 'bold', fontSize: '15px' }}>
                                        <CheckCircle2 size={20} /> Aadhaar Address Update Submitted Successfully!
                                    </div>
                                    <p style={{ fontSize: '12px', color: '#cbd5e1', margin: '0.5rem 0 1rem' }}>
                                        All stages have been approved and submitted through the official UIDAI SSUP portal.
                                    </p>
                                    <div className="detail-row" style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '10px 15px' }}>
                                        <span>Update Request Number (URN)</span>
                                        <strong style={{ fontSize: '1.25rem', color: '#4ade80', letterSpacing: '1px' }}>{sessionUrn}</strong>
                                    </div>
                                    <div className="detail-row" style={{ marginTop: '8px' }}>
                                        <span>Tracking Portal</span>
                                        <span>myaadhaar.uidai.gov.in/check-aadhaar-update-status</span>
                                    </div>
                                </div>
                            )}

                            <div className="action-row" style={{ marginTop: '0.75rem' }}>
                                <button className="secondary-button" onClick={() => window.location.reload()}>
                                    Start Another Update
                                </button>
                                <button className="secondary-button" onClick={copyDemographics} title="Copy verified details">
                                    <Copy size={15} /> Copy Details
                                </button>
                            </div>
                        </section>
                    )}
                    {inspectionEnabled && browserSessionActive && <TemporaryPortalInspection sessionId={sessionId}
                        operation={executionOperation} submitting={submittingStep} />}
                    {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                </section>
            </main>
            <footer className="footer"><span><ShieldCheck size={14} /> Built for secure, citizen-controlled assistance</span><span>Official UIDAI SSUP Copilot</span></footer>
        </div>
    );
}

function ErrorState({ message, onRetry }) {
    return <div className="error-state"><div className="error-icon"><CircleAlert size={23} /></div><h2>We need a clearer document</h2><p>{message}</p><button className="secondary-button" onClick={onRetry}>Choose another file</button></div>;
}
