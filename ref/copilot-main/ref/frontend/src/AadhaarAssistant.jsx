import { useState } from 'react';
import {
    ArrowRight,
    Check,
    CheckCircle2,
    ChevronLeft,
    CircleAlert,
    FileCheck2,
    FileUp,
    LoaderCircle,
    LockKeyhole,
    Pencil,
    ShieldCheck,
    Sparkles,
} from 'lucide-react';
import { confirmAadhaarDocument, extractAadhaarDocument, runAadhaarPipeline } from './documentApi';

const steps = [
    { label: 'Your request', short: 'Request' },
    { label: 'Your document', short: 'Upload' },
    { label: 'Review details', short: 'Review' },
    { label: 'Next steps', short: 'Result' },
];

const fields = [
    ['name', 'Name'],
    ['date_of_birth', 'Date of birth'],
    ['gender', 'Gender'],
    ['masked_aadhaar', 'Aadhaar reference'],
    ['existing_address', 'Existing address'],
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
    const [correctionField, setCorrectionField] = useState('existing_address');
    const [correctionValue, setCorrectionValue] = useState('');
    const [status, setStatus] = useState('idle');
    const [error, setError] = useState('');
    const [result, setResult] = useState(null);

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
            const response = await confirmAadhaarDocument(extraction, corrections);
            setConfirmedContext(response.confirmed_context || response);
            setStatus('idle');
            setStep(3);
        } catch (requestError) {
            setStatus('error');
            setError(requestError.message);
        }
    }

    async function continueToPipeline() {
        setStatus('processing');
        setError('');
        try {
            const response = await runAadhaarPipeline({
                message: request,
                confirmedContext,
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

    const isBusy = ['extracting', 'confirming', 'processing'].includes(status);
    const resultStatus = result?.status || result?.integration_result?.status || '';

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
                <div className="privacy-note"><LockKeyhole size={14} /> Your document stays private</div>
            </header>

            <main className="workspace">
                <aside className="intro-rail">
                    <div className="eyebrow">PERSONAL ASSISTANT <span>01</span></div>
                    <h1>One small step at a time.</h1>
                    <p className="intro-copy">We’ll help you prepare an Aadhaar address update, check the details, and show you what needs your attention.</p>
                    <div className="rail-note">
                        <ShieldCheck size={18} />
                        <span>Your approval is always required before anything moves forward.</span>
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
                            <button className="primary-button" disabled={!request.trim()} onClick={() => setStep(1)}>Continue <ArrowRight size={17} /></button>
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
                            <div className="quiet-notice"><LockKeyhole size={16} /><span>Your file is used for this review only. Never share your full Aadhaar number here.</span></div>
                        </section>
                    )}

                    {step === 2 && (
                        <section className="flow-view appear">
                            <button className="back-button" disabled={isBusy} onClick={() => setStep(1)}><ChevronLeft size={16} /> Back</button>
                            {status === 'extracting' ? (
                                <div className="loading-state"><div className="loader-ring"><LoaderCircle size={30} /></div><div className="section-kicker">Just a moment</div><h2>Reading your document...</h2><p className="section-lede">We’re looking for the details needed to prepare your update.</p></div>
                            ) : extractionData ? (
                                <>
                                    <div className="section-kicker">Check before continuing</div>
                                    <h2>Do these details look right?</h2>
                                    <p className="section-lede">These details were extracted from your document. Please verify them before continuing.</p>
                                    <div className="details-card">
                                        {fields.map(([key, label]) => (
                                            <div className="detail-row" key={key}>
                                                <span>{label}</span>
                                                <strong>{corrections[key] || fieldValue(extractionData, key) || 'Not found'}</strong>
                                                {corrections[key] && <em>corrected</em>}
                                            </div>
                                        ))}
                                    </div>
                                    {correcting && (
                                        <div className="correction-panel">
                                            <div className="field-label">Correct a detail</div>
                                            <div className="correction-row"><select value={correctionField} onChange={(event) => setCorrectionField(event.target.value)}>{fields.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input autoFocus value={correctionValue} onChange={(event) => setCorrectionValue(event.target.value)} placeholder="Enter the correct value" /></div>
                                            <button className="text-button" onClick={saveCorrection}>Save correction</button>
                                        </div>
                                    )}
                                    <div className="action-row"><button className="secondary-button" onClick={() => setCorrecting(true)}><Pencil size={16} /> Correct a detail</button><button className="primary-button" onClick={confirmDetails} disabled={isBusy}><CheckCircle2 size={17} /> Confirm details</button></div>
                                </>
                            ) : <ErrorState message={error || 'We could not read this document.'} onRetry={() => setStep(1)} />}
                        </section>
                    )}

                    {step === 3 && (
                        <section className="flow-view appear">
                            {status === 'processing' ? <div className="loading-state"><div className="loader-ring"><LoaderCircle size={30} /></div><div className="section-kicker">Working carefully</div><h2>Checking your information...</h2><p className="section-lede">We’re preparing the next step. This may take a moment.</p></div> : result ? <ResultState result={result} status={resultStatus} onRestart={() => window.location.reload()} /> : <><div className="success-mark"><Check size={23} /></div><div className="section-kicker">Details confirmed</div><h2>Your Aadhaar details are confirmed.</h2><p className="section-lede">Your confirmed details are ready for the assistant to check. No government submission has been made.</p><div className="confirmed-strip"><FileCheck2 size={19} /><span>Document reviewed and confirmed</span></div><button className="primary-button" onClick={continueToPipeline}>Continue to next step <ArrowRight size={17} /></button></>}
                        </section>
                    )}
                    {error && status !== 'error' && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                    {status === 'error' && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
                </section>
            </main>
            <footer className="footer"><span><ShieldCheck size={14} /> Built for careful, human-reviewed assistance</span><span>Local prototype · No UIDAI submission</span></footer>
        </div>
    );
}

function ErrorState({ message, onRetry }) {
    return <div className="error-state"><div className="error-icon"><CircleAlert size={23} /></div><h2>We need a clearer document</h2><p>{message}</p><button className="secondary-button" onClick={onRetry}>Choose another file</button></div>;
}

function ResultState({ result, status, onRestart }) {
    const tone = resultTone(status);
    const title = tone === 'success' ? 'Your next step is ready' : tone === 'warning' ? 'Your attention is needed' : tone === 'danger' ? 'We could not continue' : 'Your request is being reviewed';
    const reason = result.blocking_reason || result.integration_result?.blocking_reason || result.response_result?.summary || 'The assistant has recorded the current state safely.';
    return <><div className={`result-badge ${tone}`}><span /> {status.replaceAll('_', ' ') || 'current status'}</div><div className="section-kicker">Current status</div><h2>{title}</h2><p className="section-lede">{reason}</p><div className="result-detail"><LockKeyhole size={17} /><span>No real Aadhaar submission has been made. You remain in control of the next step.</span></div><button className="secondary-button" onClick={onRestart}>Start another request</button></>;
}
