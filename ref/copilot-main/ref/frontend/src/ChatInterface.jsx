import { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5001';
import ReactMarkdown from 'react-markdown';
import { Send, User, Bot, Volume2, RefreshCcw, Loader2 } from 'lucide-react';

export default function ChatInterface() {
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: 'Hello. I am your Agentic Medical Assistant. I have a team of medical, mental health, and safety agents ready to help you. How are you feeling today?',
            timestamp: new Date().toISOString()
        }
    ]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const scrollRef = useRef(null);
    const audioRef = useRef(new Audio());
    const [userId] = useState(() => 'user_' + Math.random().toString(36).substr(2, 9));

    // Auto-scroll to bottom
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const sendMessage = async () => {
        if (!input.trim() || isLoading) return;

        const userMsg = { role: 'user', content: input, timestamp: new Date().toISOString() };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const res = await axios.post(`${API_URL}/api/chat`, { message: userMsg.content, user_id: userId });

            const botMsg = {
                role: 'assistant',
                content: res.data.response,
                audioUrl: res.data.audio_url ? `${API_URL}${res.data.audio_url}` : null,
                timestamp: new Date().toISOString()
            };
            setMessages(prev => [...prev, botMsg]);

            // Auto-play audio if available
            if (res.data.audio_url) {
                playAudio(res.data.audio_url);
            }

        } catch (error) {
            console.error(error);
            setMessages(prev => [...prev, {
                role: 'system',
                content: '⚠️ Error: Could not reach the medical agents. Please try again.',
                timestamp: new Date().toISOString()
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const playAudio = (url) => {
        if (!url) return;
        audioRef.current.src = url;
        audioRef.current.play();
        setIsPlaying(true);
        audioRef.current.onended = () => setIsPlaying(false);
    };

    const resetChat = async () => {
        if (!confirm("Are you sure you want to clear the conversation history?")) return;
        try {
            await axios.post(`${API_URL}/api/reset`, { user_id: userId });
            setMessages([{
                role: 'assistant',
                content: 'Conversation reset. How can I help you now?',
                timestamp: new Date().toISOString()
            }]);
        } catch (err) {
            console.error("Reset failed", err);
        }
    };

    return (
        <div className="flex flex-col h-full">
            {/* Top Bar inside Chat */}
            <div className="p-3 border-b border-slate-700/50 flex justify-between items-center bg-slate-900/20">
                <span className="text-sm font-medium text-slate-400">
                    Session ID: <span className="font-mono text-slate-500">{userId.slice(-6)}</span>
                </span>
                <button
                    onClick={resetChat}
                    className="text-xs flex items-center gap-1 text-slate-400 hover:text-red-400 transition-colors"
                    title="Reset Session"
                >
                    <RefreshCcw className="w-3 h-3" /> Reset
                </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4" ref={scrollRef}>
                {messages.map((msg, idx) => (
                    <div
                        key={idx}
                        className={`flex gap-3 animate-fade-in ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                    >
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${msg.role === 'assistant' ? 'bg-gradient-to-br from-indigo-500 to-purple-600' :
                            msg.role === 'user' ? 'bg-slate-600' : 'bg-red-900/50'
                            }`}>
                            {msg.role === 'assistant' ? <Bot className="w-5 h-5 text-white" /> : <User className="w-5 h-5 text-white" />}
                        </div>

                        <div className={`max-w-[80%] rounded-2xl p-3 px-4 shadow-sm ${msg.role === 'user'
                            ? 'bg-blue-600/90 text-white rounded-tr-sm'
                            : 'bg-slate-800/80 text-slate-200 border border-slate-700 rounded-tl-sm'
                            }`}>
                            <div className="prose prose-invert prose-sm max-w-none">
                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                            </div>

                            {msg.audioUrl && (
                                <button
                                    onClick={() => playAudio(msg.audioUrl)}
                                    className="mt-2 flex items-center gap-2 text-xs bg-slate-950/30 px-2 py-1.5 rounded-md hover:bg-slate-950/50 transition-colors text-blue-300"
                                >
                                    <Volume2 className="w-3 h-3" /> Play Audio
                                </button>
                            )}
                        </div>
                    </div>
                ))}
                {isLoading && (
                    <div className="flex gap-3 animate-fade-in">
                        <div className="w-8 h-8 rounded-full bg-indigo-500/50 flex items-center justify-center">
                            <Bot className="w-5 h-5 text-white/50" />
                        </div>
                        <div className="bg-slate-800/50 rounded-2xl p-3 px-4 flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
                            <span className="text-sm text-slate-400">Agents are thinking...</span>
                        </div>
                    </div>
                )}
            </div>

            {/* Input */}
            <div className="p-4 bg-slate-900/30 border-t border-slate-700/50 backdrop-blur-md">
                <form
                    onSubmit={(e) => { e.preventDefault(); sendMessage(); }}
                    className="flex gap-2 relative"
                >
                    <input
                        type="text"
                        className="w-full glass-input pr-12 text-sm"
                        placeholder="Type your symptoms or questions..."
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={isLoading || !input.trim()}
                        className="absolute right-1 top-1 bottom-1 px-3 bg-blue-600 hover:bg-blue-500 rounded-md text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                    >
                        <Send className="w-4 h-4" />
                    </button>
                </form>
            </div>
        </div>
    );
}
