import { useState } from 'react';
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
} from 'lucide-react';
import { confirmAadhaarDocument, extractAadhaarDocument, launchUidaiBrowser, runAadhaarPipeline } from './documentApi';

const steps = [
    { label: 'Your request', short: 'Request' },
    { label: 'Your document', short: 'Upload' },
    { label: 'Review details', short: 'Review' },
    { label: 'Next steps', short: 'Result' },
];

const standardFields = [
    ['name', 'Full Name'],
    ['date_of_birth', 'Date of Birth'],
    ['gender', 'Gender'],
    ['masked_aadhaar', 'Aadhaar / VID Reference'],
    ['existing_address', 'Current Address'],
    ['new_address', 'New Address (to update)'],
    ['pincode', 'PIN Code'],
];

const sessionId = `aadhaar-demo-${Math.random().toString(36).slice(2, 9)}`;

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
    const [browserStatus, setBrowserStatus] = useState('');
    const [copiedNotification, setCopiedNotification] = useState('');
    const [result, setResult] = useState(null);
    const [launchingBrowser, setLaunchingBrowser] = useState(false);

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
            setConfirmedContext(response.confirmed_context || response);
            setStatus('idle');
            setStep(3);
        } catch (requestError) {
            setStatus('error');
            setError(requestError.message);
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

    async function handleLaunchBrowser() {
        setLaunchingBrowser(true);
        setBrowserStatus('');
        setError('');
        try {
            const ctxToUse = confirmedContext || {
                session_id: sessionId,
                facts: {
                    name: { value: corrections.name || fieldValue(extractionData, 'name') || 'Citizen', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    existing_address: { value: corrections.existing_address || fieldValue(extractionData, 'existing_address') || '', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    new_address: { value: corrections.new_address || '', provenance: 'user-input', status: 'confirmed', allowed_for_execution: true },
                    pincode: { value: corrections.pincode || '', provenance: 'user-input', status: 'confirmed', allowed_for_execution: true },
                    date_of_birth: { value: corrections.date_of_birth || fieldValue(extractionData, 'date_of_birth') || '', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    gender: { value: corrections.gender || fieldValue(extractionData, 'gender') || 'Male', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                    masked_aadhaar: { value: corrections.masked_aadhaar || fieldValue(extractionData, 'masked_aadhaar') || 'XXXX-XXXX-9012', provenance: 'extraction', status: 'confirmed', allowed_for_execution: true },
                },
                document_refs: file ? [file.name] : ['Uploaded_Aadhaar_Document.pdf'],
            };
            const res = await launchUidaiBrowser(ctxToUse, "0000/12345/67890", true);
            if (res.status === 'ok') {
                setBrowserStatus('Official UIDAI Portal (https://myaadhaar.uidai.gov.in/) opened in Chromium. Please complete CAPTCHA & OTP on the official portal.');
            }
        } catch (err) {
            setError(`Failed to launch browser: ${err.message}`);
        } finally {
            setLaunchingBrowser(false);
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

    const isBusy = ['extracting', 'confirming', 'processing'].includes(status) || launchingBrowser;
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
                        <div className="brand-caption">A calmer way through your next update</div>
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <button
                        className="secondary-button"
                        style={{ height: '34px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '5px' }}
                        onClick={handleLaunchBrowser}
                        disabled={launchingBrowser}
                    >
                        <Globe size={14} /> {launchingBrowser ? 'Opening...' : 'Open UIDAI Portal'}
                    </button>
                    <div className="privacy-note"><LockKeyhole size={14} /> Your document stays private</div>
                </div>
            </header>

            <main className="workspace">
                <aside className="intro-rail">
                    <div className="eyebrow">PERSONAL BUREAUCRACY <span>01</span></div>
                    <h1>One small step at a time.</h1>
                    <p className="intro-copy">We’ll help you prepare an Aadhaar address update, collect any missing information in-app, and open the official UIDAI page directly in Chromium.</p>
                    <div className="rail-note">
                        <ShieldCheck size={18} />
                        <span>Security CAPTCHA & mobile OTP are always entered directly on the official UIDAI website.</span>
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
                                    onClick={handleLaunchBrowser}
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
                            {status === 'processing' ? (
                                <div className="loading-state">
                                    <div className="loader-ring"><LoaderCircle size={30} /></div>
                                    <div className="section-kicker">Working carefully</div>
                                    <h2>Processing your request...</h2>
                                    <p className="section-lede">Validating compliance requirements against UIDAI policy rules.</p>
                                </div>
                            ) : result ? (
                                <ResultState
                                    result={result}
                                    status={resultStatus}
                                    onRestart={() => window.location.reload()}
                                    onLaunchBrowser={handleLaunchBrowser}
                                    launchingBrowser={launchingBrowser}
                                    onCopyDetails={copyDemographics}
                                />
                            ) : (
                                <>
                                    <div className="success-mark"><Check size={23} /></div>
                                    <div className="section-kicker">Details confirmed</div>
                                    <h2>Ready for Official UIDAI Submission</h2>
                                    <p className="section-lede">Your demographic data is verified. You can launch the official UIDAI page directly in Chromium.</p>
                                    
                                    <div className="confirmed-strip">
                                        <FileCheck2 size={19} />
                                        <span>Demographic details verified and ready</span>
                                    </div>

                                    {/* Dedicated Official UIDAI Portal Card */}
                                    <div className="correction-panel" style={{ width: '100%', background: 'rgba(14,165,233,0.07)', border: '1px solid rgba(14,165,233,0.3)', marginBottom: '1.25rem' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 'bold', fontSize: '13px' }}>
                                            <Globe size={18} /> Official UIDAI Portal (myAadhaar)
                                        </div>
                                        <p style={{ fontSize: '12px', color: '#94a3b8', margin: '6px 0 10px', lineHeight: 1.5 }}>
                                            Directly launches <strong>https://myaadhaar.uidai.gov.in/</strong> in Chromium.
                                        </p>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#f59e0b', marginBottom: '12px' }}>
                                            <KeyRound size={14} /> <strong>Security Protocol:</strong> Please solve CAPTCHA and enter your mobile OTP on the official UIDAI portal window.
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <button
                                                className="primary-button"
                                                style={{ flex: 1, background: 'linear-gradient(110deg, #0284c7, #0ea5e9)', color: '#fff', borderColor: '#0284c7' }}
                                                onClick={handleLaunchBrowser}
                                                disabled={launchingBrowser}
                                            >
                                                {launchingBrowser ? <><LoaderCircle size={16} className="loader-ring" /> Opening Chromium...</> : <><Globe size={16} /> Launch Official UIDAI Page in Chromium</>}
                                            </button>
                                            <button className="secondary-button" onClick={copyDemographics} title="Copy verified details">
                                                <Copy size={16} /> Copy
                                            </button>
                                        </div>
                                    </div>

                                    {browserStatus && (
                                        <div className="confirmed-strip" style={{ borderColor: '#10b981', background: 'rgba(16,185,129,0.1)', color: '#a7f3d0' }}>
                                            <CheckCircle2 size={18} style={{ color: '#10b981' }} />
                                            <span>{browserStatus}</span>
                                        </div>
                                    )}

                                    <div className="action-row" style={{ marginTop: '0.75rem' }}>
                                        <button className="secondary-button" onClick={() => continueToPipeline()} disabled={isBusy}>
                                            Run Automated Compliance Check <ArrowRight size={16} />
                                        </button>
                                    </div>
                                </>
                            )}
                        </section>
                    )}
                    {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                </section>
            </main>
            <footer className="footer"><span><ShieldCheck size={14} /> Built for secure, citizen-controlled assistance</span><span>Official UIDAI SSUP Integration</span></footer>
        </div>
    );
}

function ErrorState({ message, onRetry }) {
    return <div className="error-state"><div className="error-icon"><CircleAlert size={23} /></div><h2>We need a clearer document</h2><p>{message}</p><button className="secondary-button" onClick={onRetry}>Choose another file</button></div>;
}

function ResultState({ result, status, onRestart, onLaunchBrowser, launchingBrowser, onCopyDetails }) {
    const tone = resultTone(status);
    const isCompleted = status === 'execution_completed';

    const resp = result.response_result;
    const headline = resp?.headline || (isCompleted ? 'Aadhaar Update Submitted Successfully' : 'UIDAI Update Process');
    const summary = resp?.summary || result.blocking_reason || result.integration_result?.blocking_reason || 'Processing completed.';

    // Extract URN reference if available
    const execStepResults = result.integration_result?.execution_result?.step_results || [];
    const urn = execStepResults.find(s => s.portal_reference)?.portal_reference;

    return (
        <div className="result-card appear" style={{ width: '100%' }}>
            <div className={`result-badge ${tone}`}><span /> {status.replaceAll('_', ' ') || 'current status'}</div>
            <div className="section-kicker">UIDAI Submission Status</div>
            <h2>{headline}</h2>
            <p className="section-lede">{summary}</p>

            {/* Chromium Browser Quick Launch Button */}
            <div className="correction-panel" style={{ width: '100%', background: 'rgba(14,165,233,0.07)', border: '1px solid rgba(14,165,233,0.3)', margin: '1rem 0' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 'bold', fontSize: '13px' }}>
                        <Globe size={18} /> Official UIDAI Portal
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                        <button className="secondary-button" onClick={onCopyDetails} style={{ height: '34px', fontSize: '11px' }}>
                            <Copy size={13} /> Copy Details
                        </button>
                        <button
                            className="primary-button"
                            style={{ padding: '0.4rem 1rem', fontSize: '11px', background: '#0284c7', color: '#fff', minHeight: '34px' }}
                            onClick={onLaunchBrowser}
                            disabled={launchingBrowser}
                        >
                            {launchingBrowser ? 'Opening...' : <><ExternalLink size={14} /> Open in Chromium</>}
                        </button>
                    </div>
                </div>
                <p style={{ fontSize: '11px', color: '#94a3b8', marginTop: '8px', lineHeight: 1.4 }}>
                    Navigate to <strong>https://myaadhaar.uidai.gov.in/</strong>, solve the official CAPTCHA, and enter your 6-digit OTP directly on the UIDAI portal.
                </p>
            </div>

            {urn && (
                <div className="details-card" style={{ marginTop: '1rem', borderLeft: '4px solid #16a34a' }}>
                    <div className="detail-row">
                        <span>Update Request Number (URN)</span>
                        <strong style={{ fontSize: '1.15rem', color: '#16a34a' }}>{urn}</strong>
                    </div>
                    <div className="detail-row">
                        <span>Official Portal</span>
                        <span>UIDAI Self Service Update Portal (SSUP)</span>
                    </div>
                </div>
            )}

            {resp?.completed_actions?.length > 0 && (
                <div className="details-card" style={{ marginTop: '1rem' }}>
                    <div className="field-label" style={{ marginBottom: '0.5rem', fontWeight: 600, padding: '0 15px', paddingTop: '10px' }}>Completed Steps</div>
                    {resp.completed_actions.map((act, i) => (
                        <div key={i} className="detail-row" style={{ fontSize: '0.9rem' }}>
                            <span style={{ color: '#16a34a', fontWeight: 'bold' }}>✓</span>
                            <span>{act}</span>
                        </div>
                    ))}
                </div>
            )}

            <div className="action-row" style={{ marginTop: '1.5rem' }}>
                <button className="secondary-button" onClick={onRestart}>Start another request</button>
            </div>
        </div>
    );
}
