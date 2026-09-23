import { useState } from 'react';
import ChatInterface from './ChatInterface';
import ReportAnalyzer from './ReportAnalyzer';
import { MessageSquare, FileText, Activity } from 'lucide-react';

function App() {
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' or 'report'

  return (
    <div className="flex flex-col h-full overflow-hidden text-slate-200">
      {/* Header */}
      <header className="flex-none p-4 glass-panel m-4 mb-2 flex justify-between items-center z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-blue-500 to-emerald-500 rounded-lg shadow-lg">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400">
              Agentic Medical System
            </h1>
            <p className="text-xs text-slate-400">Multi-Agent Healthcare Assistant</p>
          </div>
        </div>

        <nav className="flex gap-2 bg-slate-800/50 p-1 rounded-lg backdrop-blur-sm border border-slate-700/50">
          <button
            onClick={() => setActiveTab('chat')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md transition-all text-sm font-medium ${
              activeTab === 'chat'
                ? 'bg-blue-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            Live Chat
          </button>
          <button
            onClick={() => setActiveTab('report')}
            className={`flex items-center gap-2 px-4 py-2 rounded-md transition-all text-sm font-medium ${
              activeTab === 'report'
                ? 'bg-emerald-600 text-white shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
            }`}
          >
            <FileText className="w-4 h-4" />
            Report Analysis
          </button>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-hidden relative p-4 pt-0">
        <div className="w-full h-full glass-panel overflow-hidden flex flex-col relative z-0">
         {activeTab === 'chat' ? <ChatInterface /> : <ReportAnalyzer />}
        </div>
      </main>
    </div>
  );
}

export default App;
