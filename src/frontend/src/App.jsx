import React from 'react';
import ConversationList from './components/ConversationList';
import ChatInterface from './components/ChatInterface';
import Settings from './components/Settings';
import AppLayout from './AppLayout'; // Import the updated AppLayout component
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
  
  // Handle conversation selection
  const handleSelectConversation = (id) => {
    selectConversation(id);
  };
  
  // Prepare sidebar content - left side
  const sidebarContent = (
    <ConversationList 
      conversations={conversations}
      currentConversationId={currentConversationId}
      onSelect={handleSelectConversation}
      onNew={createConversation}
      onDelete={deleteConversation}
      onRename={renameConversation}
    />
  );
  
  // Main content (chat interface)
  const mainContent = (
    <ChatInterface 
      conversationContext={contextForCurrentConversation} 
    />
  );
  
  // Settings panel content - right side
  const settingsContent = (
    <Settings />
  );
  
  return (
    <AppLayout
      sidebar={sidebarContent}
      content={mainContent}
      settingsPanel={settingsContent}
      apiKeyRequired={!apiKey}
    />
  );
};

export default App;