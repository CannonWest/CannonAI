import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useConversation } from '../hooks/useConversation';
import { useToast } from './ToastContext';

const ConversationContext = createContext();

const ConversationProvider = ({ children }) => {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [conversationLoaded, setConversationLoaded] = useState(false);
  
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
        setConversationLoaded(true);
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
    if (id === currentConversationId && conversationLoaded) return;
    
    try {
      setLoading(true);
      setConversationLoaded(false);
      console.log(`Loading conversation: ${id}`);
      const result = await loadConversation(id);
      
      if (result) {
        setCurrentConversationId(id);
        setConversationLoaded(true);
        setError(null);
        console.log(`Conversation loaded successfully: ${id}`);
      } else {
        toast.error('Could not load conversation');
        setError('Could not load conversation');
      }
    } catch (err) {
      console.error(`Error loading conversation: ${err}`);
      setError(err.toString());
      toast.error('Failed to load conversation');
    } finally {
      setLoading(false);
    }
  }, [currentConversationId, loadConversation, toast, conversationLoaded]);
  
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
          setConversationLoaded(false);
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
      try {
        const created = await createConversation('New Conversation');
        if (!created) {
          toast.error('Could not create a new conversation');
          return null;
        }
      } catch (err) {
        setError(err.toString());
        toast.error('Failed to create conversation: ' + err.toString());
        return null;
      }
    }
    
    try {
      // Set a loading state to show the user something is happening
      setLoading(true);
      
      // Send the user message
      const userMessage = await sendUserMessage(content);
      if (!userMessage) {
        toast.error('Failed to send message');
        return null;
      }
      
      // Start streaming the response
      const abortController = streamResponse(content);
      
      // Return the abort controller so the UI can cancel if needed
      return abortController;
    } catch (err) {
      setError(err.toString());
      
      // Provide more specific error messages based on common issues
      if (err.message?.includes('API key')) {
        toast.error('Invalid or missing API key. Please add a valid OpenAI API key in Settings.');
      } else if (err.message?.includes('429') || err.message?.includes('rate limit')) {
        toast.error('OpenAI rate limit exceeded. Please try again later.');
      } else if (err.message?.includes('Network') || err.message?.includes('timeout')) {
        toast.error('Network error. Please check your internet connection.');
      } else {
        toast.error('Failed to send message: ' + err.toString());
      }
      
      return null;
    } finally {
      setLoading(false);
    }
  }, [currentConversationId, createConversation, streamResponse, sendUserMessage, toast]);

  // Context value with conversation data and methods
  const contextForCurrentConversation = {
    currentConversation,
    messages,
    isStreaming,
    loading,
    error,
    conversationLoaded,
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
      conversationLoaded,
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
