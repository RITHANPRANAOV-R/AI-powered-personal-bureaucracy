import { useState } from 'react';
import {
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronLeft,
    CircleAlert,
    Copy,
    FileCheck2,
    FileUp,
    KeyRound,
    LoaderCircle,
    LockKeyhole,
    Pencil,
    PlusCircle,
    ShieldAlert,
    ShieldCheck,
    Workflow,
} from 'lucide-react';
import {
    confirmAadhaarDocument,
    extractAadhaarDocument,
    launchUidaiBrowser,
    runAadhaarPipeline,
    submitBrowserStep,
} from './documentApi';

const steps = [
    { label: 'Your request', short: 'Request' },
    { label: 'Your document', short: 'Upload' },
    { label: 'Review details', short: 'Review' },
    { label: 'Next steps', short: 'Result' },
];

const standardFields = [
    ['name', 'Full Name'],
    ['aadhaar_number', 'Government ID Number'],
    ['date_of_birth', 'Date of Birth'],
    ['gender', 'Gender'],
    ['masked_aadhaar', 'Masked ID / Reference Number'],
    ['existing_address', 'Current Address'],
    ['new_address', 'New Address (to update)'],
    ['pincode', 'PIN Code'],
];

const sessionId = `aadhaar-session-${Math.random().toString(36).slice(2, 9)}`;

function fieldValue(data, key) {
    const field = data?.[key];
    return typeof field === 'object' ? field?.value : field;
}

function resultTone(status = '') {
    const value = status.toLowerCase();
    if (value.includes('completed')) return 'success';
    if (value.includes('blocked') || value.includes('failed')) return 'danger';
    if (value.includes('human') || value.includes('pending') || value.includes('clarif')) return 'warning';
    return 'info';
}

export default function AadhaarAssistant() {
    const [step, setStep] = useState(0);
    const [request, setRequest] = useState('I want to update my address');
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
    const [sessionUrn, setSessionUrn] = useState('0000/12345/67890');
    const [isSessionCompleted, setIsSessionCompleted] = useState(false);
    const [submittingStep, setSubmittingStep] = useState(false);
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

    const extractionData = extraction?.data;

    async function handleFile(fileToRead) {
        if (!fileToRead) return;
        setFile(fileToRead);
        setError('');
        setStatus('extracting');
        setStep(2);
        try {
            const response = await extractAadhaarDocument(fileToRead);
            if (response.status && response.status !== 'success') {
                throw new Error(response.error || 'Some details could not be read reliably.');
            }
            setExtraction(response);
            setStatus('idle');
        } catch (requestError) {
            setStatus('error');
            setError(requestError.message);
        }
    }

    async function confirmDetails() {
        setStatus('confirming');
        setError('');
        try {
            const response = await confirmAadhaarDocument(extraction, corrections, sessionId);
            const ctx = response.confirmed_context || response;
            setConfirmedContext(ctx);
            setStatus('idle');
            setStep(3);
            // Automatically initiate interactive session on confirmation
            await startInteractiveSession(ctx);
        } catch (requestError) {
            setStatus('error');
            setError(requestError.message);
        }
    }

    async function startInteractiveSession(ctx) {
        setLaunchingBrowser(true);
        setError('');
        try {
            const extractedAadhaar = fieldValue(extractionData, 'aadhaar_number') || fieldValue(extractionData, 'masked_aadhaar') || '';
            const aadhaarVal = corrections.aadhaar_number || corrections.masked_aadhaar || extractedAadhaar || '999912345678';
            const addrVal = corrections.new_address || fieldValue(extractionData, 'new_address') || corrections.existing_address || fieldValue(extractionData, 'existing_address') || '';
            const pinVal = corrections.pincode || fieldValue(extractionData, 'pincode') || '';

            setStepAddressInputs((prev) => ({
                ...prev,
                new_address: addrVal,
                pincode: pinVal,
                house_no: prev.house_no || (addrVal.split(',')[0] || ''),
                street: prev.street || (addrVal.split(',')[1] || ''),
                locality: prev.locality || (addrVal.split(',')[2] || ''),
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

            const sessionResponse = await launchUidaiBrowser(contextToUse, "0000/12345/67890", true);
            setBrowserSessionActive(true);
            setCurrentStageData(sessionResponse.stage_info);
            setSessionUrn(sessionResponse.urn || '0000/12345/67890');
        } catch (err) {
            setError(`Could not start browser session: ${err.message}`);
        } finally {
            setLaunchingBrowser(false);
        }
    }

    async function handleAppSubmitStep() {
        if (!browserSessionActive) return;
        setSubmittingStep(true);
        setError('');
        try {
            const stepResult = await submitBrowserStep(sessionId, true, '', stepAddressInputs);
            if (currentStageData) {
                setCompletedStages((prev) => [...prev, currentStageData]);
            }
            if (stepResult.is_completed) {
                setIsSessionCompleted(true);
                setCurrentStageData(null);
                setSessionUrn(stepResult.urn);
            } else {
                setCurrentStageData(stepResult.stage_info);
                if (stepResult.urn) setSessionUrn(stepResult.urn);
            }
        } catch (err) {
            setError(`Step submission failed: ${err.message}`);
        } finally {
            setSubmittingStep(false);
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
        if (!correctionValue.trim()) return;
        setCorrections((current) => ({ ...current, [correctionField]: correctionValue.trim() }));
        setCorrecting(false);
        setCorrectionValue('');
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
                    <div className="brand-mark"><FileCheck2 size={19} /></div>
                    <div>
                        <div className="brand-name">AI-powered Personal Bureaucracy</div>
                        <div className="brand-caption">Guidance for everyday public services</div>
                    </div>
                </div>
                <div className="privacy-note"><LockKeyhole size={14} /> Your document stays private</div>
            </header>

            <main className="workspace">
                <aside className="intro-rail">
                    <div className="eyebrow">PERSONAL BUREAUCRACY</div>
                    <h1>Get things done,<br />one step at<br />a time.</h1>
                    <p className="intro-copy">We’ll help you understand what’s needed, prepare the right information, and guide you through the process.</p>
                    <div className="rail-note">
                        <ShieldCheck size={18} />
                        <span>You’re always in control.<br />Nothing is submitted without your approval.</span>
                    </div>
                    <div className="rail-orbit orbit-one" />
                    <div className="rail-orbit orbit-two" />
                </aside>

                <section className="flow-panel">
                    <nav className="stepper" aria-label="Request progress">
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
                            <textarea id="request" className="request-box" value={request} onChange={(event) => setRequest(event.target.value)} placeholder="Tell us what you need help with — updating an address, checking an application, requesting a document, or understanding a government process." rows="3" />
                            <div className="action-row">
                                <button className="primary-button" disabled={!request.trim()} onClick={() => setStep(1)}>
                                    Continue <ArrowRight size={17} />
                                </button>
                            </div>
                        </section>
                    )}

                    {step === 1 && (
                        <section className="flow-view appear">
                            <button className="back-button" onClick={() => setStep(0)}><ChevronLeft size={16} /> Back</button>
                            <div className="section-kicker">Step two</div>
                            <h2>Bring your identity document</h2>
                            <p className="section-lede">Upload a clear PDF or image. We’ll read only the details needed for your request.</p>
                            <label className="upload-zone" htmlFor="aadhaar-file">
                                <span className="upload-icon"><FileUp size={24} /></span>
                                <strong>{file ? file.name : 'Choose an identity document PDF or image'}</strong>
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
                                                Please fill in any missing information below so your request is accurate.
                                            </p>
                                        </div>
                                    )}

                                    <div className="details-card">
                                        {standardFields.map(([key, label]) => {
                                            const val = corrections[key] || fieldValue(extractionData, key);
                                            const isMissing = !val;
                                            return (
                                                <div className="detail-row" key={key}>
                                                    <span>{label}</span>
                                                    <strong style={{ color: isMissing ? '#f59e0b' : 'inherit' }}>
                                                        {val || (key === 'new_address' ? 'Click "Fill" to add new address' : key === 'pincode' ? 'Click "Fill" to add PIN' : 'Not found (click Fill to enter)')}
                                                    </strong>
                                                    {corrections[key] ? <em>updated</em> : isMissing ? (
                                                        <button
                                                            className="text-button"
                                                            style={{ color: '#0ea5e9', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '3px' }}
                                                            onClick={() => {
                                                                setCorrectionField(key);
                                                                setCorrecting(true);
                                                            }}
                                                        >
                                                            <PlusCircle size={12} /> Fill
                                                        </button>
                                                    ) : null}
                                                </div>
                                            );
                                        })}
                                    </div>

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
                                        <button className="primary-button" onClick={confirmDetails} disabled={isBusy}>
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
                            <div className="section-kicker">Step four · Guided submission</div>
                            <h2>Interactive Submission Control</h2>
                            <p className="section-lede">Your secure application page is open. Review each stage and submit using the buttons below.</p>

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
                                            <KeyRound size={15} /> <strong>Security notice:</strong> Enter the CAPTCHA and mobile verification code in the browser window, then click submit below.
                                        </div>
                                    )}

                                    {currentStageData.id === 'stage_3_address' && (
                                        <div style={{ background: 'rgba(0,0,0,0.25)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '12px', margin: '12px 0' }}>
                                            <div style={{ fontSize: '12px', fontWeight: 600, color: '#38bdf8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                <FileCheck2 size={14} /> Address fields to review and submit:
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
                                            {(!stepAddressInputs.new_address && !stepAddressInputs.house_no) && (
                                                <div style={{ fontSize: '11px', color: '#f59e0b', marginTop: '6px' }}>
                                                    ⚠️ Missing detail detected: Please enter your House No or New Address above before clicking submit.
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    <div style={{ marginTop: '1rem' }}>
                                        <button
                                            className="primary-button"
                                            style={{ width: '100%', minHeight: '44px', fontSize: '13px', background: 'linear-gradient(110deg, #0284c7, #0ea5e9)', color: '#fff', borderColor: '#0284c7', boxShadow: '0 4px 14px rgba(2,132,199,0.3)' }}
                                            onClick={handleAppSubmitStep}
                                            disabled={submittingStep}
                                        >
                                            {submittingStep ? <><LoaderCircle size={16} className="loader-ring" /> Submitting Step...</> : <><CheckCircle2 size={16} /> {currentStageData.button_label}</>}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Final Completed View */}
                            {isSessionCompleted && (
                                <div className="details-card" style={{ width: '100%', borderLeft: '4px solid #16a34a', padding: '1.25rem', background: 'rgba(22,163,74,0.08)', marginBottom: '1.25rem' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#16a34a', fontWeight: 'bold', fontSize: '15px' }}>
                                        <CheckCircle2 size={20} /> Request submitted successfully!
                                    </div>
                                    <p style={{ fontSize: '12px', color: '#cbd5e1', margin: '0.5rem 0 1rem' }}>
                                        All stages have been reviewed and submitted.
                                    </p>
                                    <div className="detail-row" style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '8px', padding: '10px 15px' }}>
                                        <span>Update Request Number (URN)</span>
                                        <strong style={{ fontSize: '1.25rem', color: '#4ade80', letterSpacing: '1px' }}>{sessionUrn}</strong>
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
                    {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                </section>
            </main>
            <footer className="footer" aria-hidden="true" />
        </div>
    );
}

function ErrorState({ message, onRetry }) {
    return <div className="error-state"><div className="error-icon"><CircleAlert size={23} /></div><h2>We need a clearer document</h2><p>{message}</p><button className="secondary-button" onClick={onRetry}>Choose another file</button></div>;
}
