import { FileCheck2, HelpCircle, LockKeyhole, Menu, MessageCircle, X } from 'lucide-react';
import { useState } from 'react';
import AadhaarAssistant from './AadhaarAssistant';

function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="app-frame">
      <button className="mobile-menu-button" aria-label="Open menu" onClick={() => setMenuOpen(true)}><Menu size={19} /></button>
      <aside className={`app-sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="sidebar-head"><div className="sidebar-badge"><FileCheck2 size={19} /></div><span className="sidebar-title">Personal Bureaucracy</span><button className="close-menu" aria-label="Close menu" onClick={() => setMenuOpen(false)}><X size={18} /></button></div>
        <nav className="side-nav">
          <span className="nav-heading">YOUR SPACE</span>
          <span className="nav-link selected"><MessageCircle size={16} aria-hidden="true" />Assistant</span>
          <span className="nav-link"><LockKeyhole size={16} aria-hidden="true" />Personal Vault</span>
        </nav>
        <div className="sidebar-bottom"><div className="help-card"><HelpCircle size={17} /><div><strong>Need help?</strong><span>We’ll guide you through each step.</span></div></div></div>
      </aside>
      {menuOpen && <button className="scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}
      <div className="main-column"><AadhaarAssistant /></div>
    </div>
  );
}

export default App;
