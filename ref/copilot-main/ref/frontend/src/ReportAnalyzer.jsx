import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5001';
import ReactMarkdown from 'react-markdown';
import { UploadCloud, FileText, AlertTriangle, CheckCircle, Loader2, Activity } from 'lucide-react';

export default function ReportAnalyzer() {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [analysis, setAnalysis] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleFileChange = (e) => {
        const selected = e.target.files[0];
        if (selected) {
            setFile(selected);
            setPreview(URL.createObjectURL(selected));
            setAnalysis(null);
            setError('');
        }
    };

    const handleUpload = async () => {
        if (!file) return;

        setIsLoading(true);
        setError('');

        const formData = new FormData();
        formData.append('image', file);

        try {
            const res = await axios.post(`${API_URL}/api/report`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setAnalysis(res.data);
        } catch (err) {
            console.error(err);
            setError('Failed to analyze report. Please ensure the backend is running and the file is valid.');
        } finally {
            setIsLoading(false);
        }
    };





    return (
        <div className="h-full overflow-y-auto p-6 md:p-12 max-w-4xl mx-auto">
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-white mb-2">Medical Report Analysis</h2>
                <p className="text-slate-400">Upload a scan, lab report, or prescription for instant AI analysis.</p>
            </div>

            <div className="grid md:grid-cols-2 gap-8 items-start">
                {/* Upload Section */}
                <div className="space-y-4">
                    <div
                        className={`border-2 border-dashed rounded-2xl h-64 flex flex-col items-center justify-center transition-all bg-slate-800/30 ${file ? 'border-emerald-500/50 bg-emerald-900/10' : 'border-slate-600 hover:border-blue-400/50 hover:bg-slate-800/60'
                            }`}
                    >
                        {preview ? (
                            <img src={preview} alt="Upload Preview" className="h-full w-full object-contain rounded-xl p-2" />
                        ) : (
                            <label className="flex flex-col items-center cursor-pointer w-full h-full justify-center p-6">
                                <UploadCloud className="w-12 h-12 text-slate-500 mb-4" />
                                <span className="text-slate-300 font-medium">Click to Upload</span>
                                <span className="text-slate-500 text-sm mt-1">Images (JPG, PNG) only</span>
                                <input type="file" className="hidden" accept="image/*" onChange={handleFileChange} />
                            </label>
                        )}
                    </div>

                    <button
                        onClick={handleUpload}
                        disabled={!file || isLoading}
                        className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {isLoading ? <Loader2 className="animate-spin w-4 h-4" /> : <FileText className="w-4 h-4" />}
                        {isLoading ? 'Analyzing...' : 'Analyze Report'}
                    </button>

                    {error && (
                        <div className="p-3 bg-red-900/20 border border-red-500/30 rounded-lg text-red-300 text-sm flex gap-2 items-center">
                            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}
                </div>

                {/* Results Section */}
                <div className="bg-slate-900/50 rounded-2xl glass-panel min-h-[400px] border-none p-6 relative">
                    {!analysis && !isLoading && (
                        <div className="absolute inset-0 flex items-center justify-center text-slate-600 flex-col gap-2">
                            <Activity className="w-12 h-12 opacity-20" />
                            <p className="text-sm">Results will appear here</p>
                        </div>
                    )}

                    {isLoading && (
                        <div className="absolute inset-0 flex items-center justify-center flex-col gap-3">
                            <div className="relative w-16 h-16">
                                <div className="absolute inset-0 border-4 border-slate-700/50 rounded-full"></div>
                                <div className="absolute inset-0 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                            </div>
                            <p className="text-emerald-400 font-mono text-sm animate-pulse">Scanning document...</p>
                        </div>
                    )}

                    {analysis && (
                        <div className="animate-fade-in space-y-4">
                            <div className="flex justify-between items-start">
                                <div className="flex items-center gap-2 text-emerald-400 mb-2">
                                    <CheckCircle className="w-5 h-5" />
                                    <span className="font-bold">Analysis Complete</span>
                                </div>

                            </div>

                            <div className="prose prose-invert prose-emerald max-w-none text-sm leading-relaxed">
                                <ReactMarkdown>{analysis.analysis}</ReactMarkdown>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
