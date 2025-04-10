import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useConversation } from '../hooks/useConversation';
import { useToast } from './ToastContext';

const ConversationContext = createContext();

const ConversationProvider = ({ children }) => {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const {
    loadConversations,
    loadConversation,
    newConversation,
    updateCurrentConversation,
    removeConversation,
    sendUserMessage,
    streamResponse,
    messages,
    currentConversation,
    isStreaming
  } = useConversation();
  
  const toast = useToast();
  
  // Load conversations on mount
  useEffect(() => {
    console.log("ConversationProvider: Loading initial conversations");
    fetchConversations();
  }, []);
  
  const fetchConversations = useCallback(async () => {
    try {
      setLoading(true);
      const data = await loadConversations();
      setConversations(data || []);
      setError(null);
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, [loadConversations, toast]);
  
  // Create a new conversation
  const createConversation = useCallback(async (name, systemMessage) => {
    try {
      setLoading(true);
      const created = await newConversation(name, systemMessage);
      if (created) {
        setConversations(prev => [created, ...prev]);
        setCurrentConversationId(created.id);
        toast.success('New conversation created');
      }
      return created;
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to create conversation');
      return null;
    } finally {
      setLoading(false);
    }
  }, [newConversation, toast]);
  
  // Select and load a conversation
  const selectConversation = useCallback(async (id) => {
    if (id === currentConversationId) return;
    
    try {
      setLoading(true);
      await loadConversation(id);
      setCurrentConversationId(id);
      setError(null);
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to load conversation');
    } finally {
      setLoading(false);
    }
  }, [currentConversationId, loadConversation, toast]);
  
  // Delete a conversation
  const deleteConversation = useCallback(async (id) => {
    try {
      setLoading(true);
      const success = await removeConversation(id);
      
      if (success) {
        setConversations(prev => prev.filter(conv => conv.id !== id));
        
        // If current conversation was deleted, select another one or clear
        if (currentConversationId === id) {
          setCurrentConversationId(null);
        }
        
        toast.success('Conversation deleted');
      }
      
      return success;
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to delete conversation');
      return false;
    } finally {
      setLoading(false);
    }
  }, [currentConversationId, removeConversation, toast]);
  
  // Rename a conversation
  const renameConversation = useCallback(async (id, newName) => {
    try {
      setLoading(true);
      const updated = await updateCurrentConversation({ name: newName });
      
      if (updated) {
        // Update in conversations list
        setConversations(prev => 
          prev.map(conv => conv.id === id ? { ...conv, name: newName } : conv)
        );
        toast.success('Conversation renamed');
      }
      
      return updated;
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to rename conversation');
      return null;
    } finally {
      setLoading(false);
    }
  }, [updateCurrentConversation, toast]);
  
  // Send a user message and get an AI response
  const sendMessage = useCallback(async (content) => {
    if (!currentConversationId) {
      // Create a new conversation if none exists
      const created = await createConversation('New Conversation');
      if (!created) return null;
    }
    
    try {
      // Send the user message
      const userMessage = await sendUserMessage(content);
      if (!userMessage) return null;
      
      // Start streaming the response
      streamResponse(content);
      
      return userMessage;
    } catch (err) {
      setError(err.toString());
      toast.error('Failed to send message');
      return null;
    }
  }, [currentConversationId, createConversation, sendUserMessage, streamResponse, toast]);
  
  // Context value with conversation data and methods
  const contextForCurrentConversation = {
    currentConversation,
    messages,
    isStreaming,
    sendMessage,
    navigateToMessage: async (messageId) => {
      // Implement navigation to specific message
    }
  };
  
  return (
    <ConversationContext.Provider value={{
      conversations,
      currentConversationId,
      loading,
      error,
      createConversation,
      selectConversation,
      deleteConversation,
      renameConversation,
      sendMessage,
      contextForCurrentConversation
    }}>
      {children}
    </ConversationContext.Provider>
  );
};

// Export the provider
export { ConversationProvider };

// Export the hook using the same pattern as other context files
export const useConversations = () => {
  const context = useContext(ConversationContext);
  if (context === undefined) {
    throw new Error('useConversations must be used within a ConversationProvider');
  }
  return context;
};
