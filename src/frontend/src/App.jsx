import React, { useState, useEffect } from 'react';
import './styles.css';
import ChatInterface from './components/ChatInterface';
import ConversationList from './components/ConversationList';
import Settings from './components/Settings';
import { AuthProvider } from './context/AuthContext';
import { SettingsProvider } from './context/SettingsContext';

function Debug() {
  const [debug, setDebug] = useState('Initializing...');
  
  useEffect(() => {
    setDebug('App mounted');
    
    // Log window size
    const updateDebugInfo = () => {
      setDebug(`Window: ${window.innerWidth}x${window.innerHeight}, Ready: ${document.readyState}`);
    };
    
    window.addEventListener('resize', updateDebugInfo);
    updateDebugInfo();
    
    return () => window.removeEventListener('resize', updateDebugInfo);
  }, []);
  
  return <div className="debug-info">{debug}</div>;
}

// Mock conversation data for initial display
const MOCK_CONVERSATIONS = [
  { id: '1', name: 'Sample Conversation 1', created_at: new Date().toISOString() },
  { id: '2', name: 'Sample Conversation 2', created_at: new Date().toISOString() }
];

function ConversationController() {
  const [conversations, setConversations] = useState(MOCK_CONVERSATIONS);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [messages, setMessages] = useState([]);

  // Mock functions
  const handleSelect = (id) => {
    console.log("Selected conversation:", id);
    const selected = conversations.find(c => c.id === id);
    setCurrentConversation(selected);
    // Mock messages
    setMessages([
      { id: 'm1', role: 'user', content: 'Hello there!', timestamp: new Date().toISOString() },
      { id: 'm2', role: 'assistant', content: 'Hi! How can I help you today?', timestamp: new Date().toISOString() }
    ]);
  };

  const handleNew = () => {
    const newId = Date.now().toString();
    const newConv = { id: newId, name: 'New Conversation', created_at: new Date().toISOString() };
    setConversations([newConv, ...conversations]);
    setCurrentConversation(newConv);
    setMessages([]);
  };

  const handleDelete = (id) => {
    setConversations(conversations.filter(c => c.id !== id));
    if (currentConversation?.id === id) {
      setCurrentConversation(null);
      setMessages([]);
    }
  };

  const handleRename = (id, newName) => {
    setConversations(conversations.map(c => 
      c.id === id ? {...c, name: newName} : c
    ));
    if (currentConversation?.id === id) {
      setCurrentConversation({...currentConversation, name: newName});
    }
  };

  // Create the context object
  const conversationContext = {
    conversations,
    currentConversation,
    messages,
    loadConversation: handleSelect,
    newConversation: handleNew,
    removeConversation: handleDelete,
    updateCurrentConversation: (updates) => {
      if (!currentConversation) return;
      const updated = {...currentConversation, ...updates};
      setCurrentConversation(updated);
      setConversations(conversations.map(c => 
        c.id === updated.id ? updated : c
      ));
    },
    isStreaming: false,
    sendUserMessage: (content) => {
      console.log("Would send:", content);
      // Mock sending a message
      const userMsg = { 
        id: `user-${Date.now()}`, 
        role: 'user', 
        content, 
        timestamp: new Date().toISOString() 
      };
      setMessages([...messages, userMsg]);
      return userMsg;
    },
    streamResponse: (content) => {
      console.log("Would stream response for:", content);
      // In a real app, this would connect to the WebSocket
    },
    navigateHistory: (messageId) => {
      console.log("Would navigate to:", messageId);
    }
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <ConversationList
          conversations={conversations}
          currentConversationId={currentConversation?.id}
          onSelect={handleSelect}
          onNew={handleNew}
          onDelete={handleDelete}
          onRename={handleRename}
        />
      </aside>
      
      <main className="main-content">
        <ChatInterface conversationContext={conversationContext} />
      </main>
      
      <aside className="settings-panel">
        <Settings />
      </aside>
    </div>
  );
}

function App() {
  console.log("App rendering");
  
  return (
    <AuthProvider>
      <SettingsProvider>
        <div className="app">
          <header className="app-header">
            <h1>CannonAI Chat</h1>
          </header>
          
          <ConversationController />
          
          <footer className="app-footer">
            <p>CannonAI Chat Interface - Version 1.0</p>
          </footer>
          
          <Debug />
        </div>
      </SettingsProvider>
    </AuthProvider>
  );
}

export default App;
