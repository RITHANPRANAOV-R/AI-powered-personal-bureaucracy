import { useState } from 'react';
import {
    ArrowRight,
    CheckCircle2,
    ChevronLeft,
    CircleAlert,
    Copy,
    FileCheck2,
    FileUp,
    KeyRound,
    Landmark,
    LoaderCircle,
    LockKeyhole,
    Pencil,
    PlusCircle,
    ShieldAlert,
    ShieldCheck,
    SlidersHorizontal,
    Workflow,
} from 'lucide-react';
import {
    confirmAadhaarDocument,
    extractAadhaarDocument,
    launchUidaiBrowser,
    runAadhaarPipeline,
    submitBrowserStep,
} from './documentApi';

const standardFields = [
    ['name', 'Full Name'],
    ['aadhaar_number', 'Identity / Reference Number'],
    ['date_of_birth', 'Date of Birth'],
    ['gender', 'Gender'],
    ['masked_aadhaar', 'Masked Reference / VID'],
    ['existing_address', 'Current Address'],
    ['new_address', 'Updated Address'],
    ['pincode', 'Postal / PIN Code'],
];

const sessionId = `session-${Math.random().toString(36).slice(2, 9)}`;

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
    const [request, setRequest] = useState('');
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
                document_refs: file ? [file.name] : ['Uploaded_Document.pdf'],
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
        setCopiedNotification('Details copied to clipboard!');
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
                    <div className="brand-mark"><Landmark size={20} /></div>
                    <div className="brand-text-block">
                        <div className="brand-title-line">
                            <span className="brand-name">AI-powered Personal Bureaucracy</span>
                        </div>
                        <div className="brand-subtitle">Public Service Procedure & Statutory Execution Portal</div>
                    </div>
                </div>
                <div className="topbar-meta">
                    <div className="system-status-chip">
                        <span className="status-indicator-dot"></span>
                        <span>System Active</span>
                    </div>
                    <div className="vault-consent-chip">
                        <ShieldCheck size={14} /> Vault Consent Active
                    </div>
                </div>
            </header>

            <main className="workspace">
                <div className="gov-content-wrapper">
                    {step === 0 && (
                        <div className="intake-section appear">
                            <div className="citizen-intake-header">
                                <div className="intake-eyebrow-wrap">
                                    <span className="intake-step-num">01</span>
                                    <span className="intake-eyebrow-text">CITIZEN INTAKE</span>
                                    <span className="intake-eyebrow-line"></span>
                                </div>
                                <div className="intake-header-actions">
                                    <div className="pill-badge consent-pill"><ShieldCheck size={13} /> Vault Consent Active</div>
                                    <div className="pill-badge options-pill"><SlidersHorizontal size={13} /> Workflow Options</div>
                                </div>
                            </div>
                            <h1 className="citizen-hero-title">
                                Initiate Your <span className="highlight-tag">Administrative</span> Request
                            </h1>
                            <p className="citizen-hero-subtitle">
                                Enter your administrative request in plain language. The system retrieves statutory rules, verifies vault facts, and provides full human oversight.
                            </p>

                            <div className="official-form-card">
                                <div className="card-header-bar">
                                    <span className="card-section-label">Request Details</span>
                                    <span className="card-section-hint">Plain citizen language (e.g. certificate renewal, statutory request, or status tracking)</span>
                                </div>
                                <textarea
                                    id="request"
                                    className="official-textarea"
                                    value={request}
                                    onChange={(event) => setRequest(event.target.value)}
                                    placeholder="Type your official administrative request (e.g., 'Submit an application for certificate renewal' or 'Track status of my official submission')..."
                                    rows="4"
                                />
                                <div className="examples-container">
                                    <span className="examples-heading">Examples:</span>
                                    <div className="examples-chips-list">
                                        <button
                                            type="button"
                                            className="example-pill-btn"
                                            onClick={() => setRequest('Submit an application for certificate renewal')}
                                        >
                                            Submit an application for certificate renewal
                                        </button>
                                        <button
                                            type="button"
                                            className="example-pill-btn"
                                            onClick={() => setRequest('Track status of my official submission with reference ID')}
                                        >
                                            Track status of my official submission with reference ID
                                        </button>
                                        <button
                                            type="button"
                                            className="example-pill-btn"
                                            onClick={() => setRequest('Update permanent address or demographic records')}
                                        >
                                            Update permanent address or demographic records
                                        </button>
                                        <button
                                            type="button"
                                            className="example-pill-btn"
                                            onClick={() => setRequest('Check eligibility and document requirements for public service')}
                                        >
                                            Check eligibility and document requirements for public service
                                        </button>
                                    </div>
                                </div>
                                <div className="card-action-bar">
                                    <div className="audit-tags-group">
                                        <span className="audit-tag">Protocol: <strong>APB-GOV-2026</strong></span>
                                        <span className="audit-tag">Audit: <strong className="active-green">Active</strong></span>
                                    </div>
                                    <button
                                        type="button"
                                        className="official-primary-btn"
                                        disabled={!request.trim()}
                                        onClick={() => setStep(1)}
                                    >
                                        Begin Application Workflow <ArrowRight size={16} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 1 && (
                        <div className="official-form-card appear">
                            <div className="step-back-row">
                                <button type="button" className="gov-back-btn" onClick={() => setStep(0)}>
                                    <ChevronLeft size={16} /> Return to Citizen Intake
                                </button>
                                <span className="step-kicker-tag">02 DOCUMENT VERIFICATION</span>
                            </div>
                            <h2 className="step-title">Provide Supporting Documentation</h2>
                            <p className="step-desc">Upload a clear official document (PDF or image). Extracted information remains encrypted and client-confidential under statutory privacy rules.</p>
                            <label className="gov-upload-zone" htmlFor="document-file">
                                <div className="upload-icon-circle"><FileUp size={26} /></div>
                                <strong>{file ? file.name : 'Select or drop official document (PDF, PNG, JPG)'}</strong>
                                <span>Maximum allowable file size: 25 MB · High resolution recommended</span>
                                <input id="document-file" type="file" accept=".pdf,.png,.jpg,.jpeg,image/*,application/pdf" onChange={(event) => handleFile(event.target.files?.[0])} />
                            </label>
                            <div className="gov-notice-banner">
                                <LockKeyhole size={16} />
                                <span>Document verification is conducted in local memory under strict privacy safeguards.</span>
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="official-form-card appear">
                            <div className="step-back-row">
                                <button type="button" className="gov-back-btn" disabled={isBusy} onClick={() => setStep(1)}>
                                    <ChevronLeft size={16} /> Return to Document Upload
                                </button>
                                <span className="step-kicker-tag">03 STATUTORY RECORD VERIFICATION</span>
                            </div>
                            {status === 'extracting' ? (
                                <div className="loading-state">
                                    <div className="loader-ring"><LoaderCircle size={32} /></div>
                                    <h2>Parsing Document Information...</h2>
                                    <p>Verifying statutory identity and address attributes against intake specifications.</p>
                                </div>
                            ) : extractionData ? (
                                <>
                                    <h2 className="step-title">Verify & Authorize Record Details</h2>
                                    <p className="step-desc">The following attributes were parsed from your uploaded documentation. Verify each field and amend any missing attributes before proceeding.</p>

                                    {hasMissingCriticalData && (
                                        <div className="gov-alert-banner">
                                            <ShieldAlert size={16} />
                                            <div>
                                                <strong>Missing Required Attributes Detected</strong>
                                                <p>Please enter the required information below to ensure statutory compliance during portal submission.</p>
                                            </div>
                                        </div>
                                    )}

                                    <div className="gov-ledger-table">
                                        {standardFields.map(([key, label]) => {
                                            const val = corrections[key] || fieldValue(extractionData, key);
                                            const isMissing = !val;
                                            return (
                                                <div className="ledger-row" key={key}>
                                                    <span className="ledger-label">{label}</span>
                                                    <span className={`ledger-value ${isMissing ? 'val-missing' : ''}`}>
                                                        {val || (key === 'new_address' ? 'Pending input (click Fill to add)' : key === 'pincode' ? 'Pending input' : 'Not located in document')}
                                                    </span>
                                                    <div className="ledger-action">
                                                        {corrections[key] ? (
                                                            <span className="updated-tag">verified edit</span>
                                                        ) : isMissing ? (
                                                            <button
                                                                type="button"
                                                                className="ledger-fill-btn"
                                                                onClick={() => {
                                                                    setCorrectionField(key);
                                                                    setCorrecting(true);
                                                                }}
                                                            >
                                                                <PlusCircle size={13} /> Fill
                                                            </button>
                                                        ) : null}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>

                                    {correcting && (
                                        <div className="gov-edit-drawer">
                                            <div className="drawer-title">Amend Record Attribute</div>
                                            <div className="drawer-inputs">
                                                <select value={correctionField} onChange={(event) => setCorrectionField(event.target.value)}>
                                                    {standardFields.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                                                </select>
                                                <input
                                                    autoFocus
                                                    value={correctionValue}
                                                    onChange={(event) => setCorrectionValue(event.target.value)}
                                                    placeholder={`Enter statutory value for ${standardFields.find(f => f[0] === correctionField)?.[1] || 'attribute'}`}
                                                />
                                            </div>
                                            <button type="button" className="gov-save-btn" onClick={saveCorrection}>Save Value</button>
                                        </div>
                                    )}

                                    <div className="ledger-footer-actions">
                                        <div className="sub-actions">
                                            <button type="button" className="gov-secondary-btn" onClick={() => setCorrecting(true)}>
                                                <Pencil size={15} /> Edit / Append Field
                                            </button>
                                            <button type="button" className="gov-secondary-btn" onClick={copyDemographics}>
                                                <Copy size={15} /> Copy Record Details
                                            </button>
                                        </div>
                                        <button type="button" className="official-primary-btn" onClick={confirmDetails} disabled={isBusy}>
                                            <CheckCircle2 size={16} /> Authorize & Proceed to Portal →
                                        </button>
                                    </div>
                                    {copiedNotification && <div className="toast-success">✓ {copiedNotification}</div>}
                                </>
                            ) : <ErrorState message={error || 'Unable to parse document records.'} onRetry={() => setStep(1)} />}
                        </div>
                    )}

                    {step === 3 && (
                        <div className="official-form-card appear">
                            <div className="step-back-row">
                                <span className="step-kicker-tag">04 STATUTORY PORTAL EXECUTION</span>
                            </div>
                            <h2 className="step-title">Portal Submission & Review</h2>
                            <p className="step-desc">The official administrative portal session is active in the browser. Review each statutory step and submit using the authorization controls below.</p>

                            {/* Completed Stages History */}
                            {completedStages.length > 0 && (
                                <div className="completed-stages-card">
                                    <div className="completed-header">Completed Submission Steps</div>
                                    {completedStages.map((st, i) => (
                                        <div key={i} className="completed-row">
                                            <span className="check-badge">✓ Step 0{st.step_number}</span>
                                            <span className="stage-title">{st.title}</span>
                                            <span className="submitted-tag">submitted</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Active Stage Consent Box */}
                            {currentStageData && !isSessionCompleted && (
                                <div className="stage-execution-box">
                                    <div className="execution-header">
                                        <div className="stage-name"><Workflow size={17} /> Step 0{currentStageData.step_number}: {currentStageData.title}</div>
                                        <span className="stage-badge">Awaiting Authorization</span>
                                    </div>
                                    <p className="stage-instruction">{currentStageData.description}</p>

                                    {currentStageData.requires_portal_interaction && (
                                        <div className="security-notice-strip">
                                            <KeyRound size={15} /> <strong>Security Verification:</strong> Enter any required CAPTCHA or OTP prompt directly in the browser window, then authorize submission below.
                                        </div>
                                    )}

                                    {currentStageData.id === 'stage_3_address' && (
                                        <div className="prepopulate-grid-wrap">
                                            <div className="prepopulate-title"><Workflow size={14} /> Demographic & Address Fields to Prepopulate & Submit:</div>
                                            <div className="prepopulate-fields-grid">
                                                <div>
                                                    <label>House / Flat / Building No</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.house_no}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, house_no: e.target.value }))}
                                                        placeholder="e.g. Flat 402, Lotus Apts"
                                                    />
                                                </div>
                                                <div>
                                                    <label>Street / Road / Lane</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.street}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, street: e.target.value }))}
                                                        placeholder="e.g. 12th Main Road"
                                                    />
                                                </div>
                                                <div>
                                                    <label>Area / Locality / Sector</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.locality}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, locality: e.target.value }))}
                                                        placeholder="e.g. Koramangala 4th Block"
                                                    />
                                                </div>
                                                <div>
                                                    <label>PIN Code</label>
                                                    <input
                                                        type="text"
                                                        maxLength={6}
                                                        value={stepAddressInputs.pincode}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, pincode: e.target.value }))}
                                                        placeholder="6-digit PIN"
                                                    />
                                                </div>
                                                <div className="full-width-field">
                                                    <label>Full Combined Address</label>
                                                    <input
                                                        type="text"
                                                        value={stepAddressInputs.new_address}
                                                        onChange={(e) => setStepAddressInputs(prev => ({ ...prev, new_address: e.target.value }))}
                                                        placeholder="Full combined new address..."
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <button
                                        type="button"
                                        className="execute-stage-btn"
                                        onClick={handleAppSubmitStep}
                                        disabled={submittingStep}
                                    >
                                        {submittingStep ? <><LoaderCircle size={16} className="loader-ring" /> Authorizing Submission...</> : <><CheckCircle2 size={16} /> {currentStageData.button_label}</>}
                                    </button>
                                </div>
                            )}

                            {/* Final Completed View */}
                            {isSessionCompleted && (
                                <div className="receipt-certificate-card">
                                    <div className="receipt-badge-title">
                                        <CheckCircle2 size={22} /> Application Submitted Successfully!
                                    </div>
                                    <p className="receipt-desc">All procedural stages have been validated and submitted through the official portal.</p>
                                    <div className="receipt-row-urn">
                                        <span>Update Request Number (URN)</span>
                                        <strong>{sessionUrn}</strong>
                                    </div>
                                    <div className="receipt-row-tracking">
                                        <span>Tracking Status</span>
                                        <span>Official Portal Verification Active</span>
                                    </div>
                                </div>
                            )}

                            <div className="stage-bottom-actions">
                                <button type="button" className="gov-secondary-btn" onClick={() => window.location.reload()}>
                                    Start Another Application Workflow
                                </button>
                                <button type="button" className="gov-secondary-btn" onClick={copyDemographics}>
                                    <Copy size={15} /> Copy Record Details
                                </button>
                            </div>
                        </div>
                    )}
                    {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                </div>
            </main>
        </div>
    );
}

function ErrorState({ message, onRetry }) {
    return <div className="error-state"><div className="error-icon"><CircleAlert size={23} /></div><h2>We need a clearer document</h2><p>{message}</p><button className="secondary-button" onClick={onRetry}>Choose another file</button></div>;
}
