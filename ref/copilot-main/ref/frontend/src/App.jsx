import { HelpCircle, Landmark, Menu, X } from 'lucide-react';
import { useState } from 'react';
import AadhaarAssistant from './AadhaarAssistant';

function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="app-frame">
      <button className="mobile-menu-button" aria-label="Open menu" onClick={() => setMenuOpen(true)}><Menu size={19} /></button>
      <aside className={`app-sidebar ${menuOpen ? 'open' : ''}`}>
        <div className="sidebar-head">
          <div className="sidebar-badge"><Landmark size={17} /></div>
          <span className="sidebar-title">AI-powered<br />Personal Bureaucracy</span>
          <button className="close-menu" aria-label="Close menu" onClick={() => setMenuOpen(false)}><X size={18} /></button>
        </div>
        <nav className="side-nav">
          <span className="nav-heading">CITIZEN SERVICES</span>
          <a className="nav-link selected" href="#assistant"><span className="nav-dot" />Start an intake</a>
          <a className="nav-link" href="#coming-soon"><span className="nav-dot muted" />More services <small>soon</small></a>
        </nav>
        <div className="sidebar-bottom">
          <div className="help-card"><HelpCircle size={17} /><div><strong>Need assistance?</strong><span>Step-by-step statutory guidance.</span></div></div>
          <span className="privacy-label">Statutory Human Oversight · Secure Session</span>
        </div>
      </aside>
      {menuOpen && <button className="scrim" aria-label="Close menu" onClick={() => setMenuOpen(false)} />}
      <div className="main-column"><AadhaarAssistant /></div>
    </div>
  );
}

export default App;
