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
  
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    
    if (sidebarOpen) {
      document.addEventListener('click', handleClickOutside);
    }
    
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [sidebarOpen]);
  
  // Toggle settings panel
  const toggleSettings = () => {
    setShowSettings(!showSettings);
  };
  
  return (
    <div className="app-layout">
      {/* Hamburger menu for mobile */}
      <button className="hamburger-menu" onClick={toggleSidebar}>
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
            Settings
          </button>
          {!apiKey && <div className="api-key-notice">API Key Required</div>}
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
