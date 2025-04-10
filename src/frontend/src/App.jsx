import React, { useState, useEffect } from 'react';
import ConversationList from './components/ConversationList';
import ChatInterface from './components/ChatInterface';
import Settings from './components/Settings';
import { useAuth } from './context/AuthContext';
import { useConversations } from './context/ConversationContext';
import './styles.css';

const App = () => {
  const { apiKey } = useAuth();
  const { 
    conversations, 
    currentConversationId, 
    createConversation, 
    deleteConversation, 
    renameConversation, 
    selectConversation,
    contextForCurrentConversation
  } = useConversations();
  
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768);
  const [showSettings, setShowSettings] = useState(false);
  
  // Handle responsive sidebar behavior
  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  // Close sidebar on conversation selection in mobile view
  const handleSelectConversation = (id) => {
    selectConversation(id);
    if (window.innerWidth <= 768) {
      setSidebarOpen(false);
    }
  };
  
  // Handle click outside sidebar to close it on mobile
  useEffect(() => {
    const handleClickOutside = (e) => {
      const sidebar = document.querySelector('.sidebar');
      const hamburgerMenu = document.querySelector('.hamburger-menu');
      
      if (sidebarOpen && 
          sidebar && 
          !sidebar.contains(e.target) && 
          hamburgerMenu && 
          !hamburgerMenu.contains(e.target)) {
        setSidebarOpen(false);
      }
    };
    
    if (sidebarOpen && window.innerWidth <= 768) {
      document.addEventListener('click', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [sidebarOpen]);
  
  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 768) {
        setSidebarOpen(true);
      } else {
        setSidebarOpen(false);
      }
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  // Toggle settings panel
  const toggleSettings = () => {
    setShowSettings(!showSettings);
  };
  
  return (
    <div className="app-layout">
      {/* Hamburger menu for mobile */}
      <button className="hamburger-menu" onClick={toggleSidebar} aria-label="Toggle sidebar">
        <span></span>
      </button>
      
      {/* Sidebar with conversations */}
      <div className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
        <ConversationList 
          conversations={conversations}
          currentConversationId={currentConversationId}
          onSelect={handleSelectConversation}
          onNew={createConversation}
          onDelete={deleteConversation}
          onRename={renameConversation}
        />
        
        <div className="sidebar-footer">
          <button 
            className="settings-button"
            onClick={toggleSettings}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"></circle>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
            </svg>
            Settings
          </button>
          
          {!apiKey && (
            <div className="api-key-notice">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"></path>
                <path d="M12 8v4"></path>
                <path d="M12 16h.01"></path>
              </svg>
              API Key Required
            </div>
          )}
        </div>
      </div>
      
      {/* Main content area */}
      <div className="content-area">
        {showSettings ? (
          <Settings onClose={() => setShowSettings(false)} />
        ) : (
          <ChatInterface conversationContext={contextForCurrentConversation} />
        )}
      </div>
    </div>
  );
};

export default App;