import { useState, useEffect, useCallback, useRef } from 'react';
import { 
  getConversations, 
  getConversationById, 
  createConversation, 
  updateConversation,
  deleteConversation,
  sendMessage,
  getMessages,
  navigateToMessage,
  streamChat
} from '../services/api';

export const useConversation = (initialConversationId = null) => {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState(null);
  
  // Ref to store the active streaming request
  const streamingRef = useRef(null);
  
  // Function to load all conversations
  const loadConversations = useCallback(async () => {
    try {
      setLoading(true);
      console.log("Loading conversations...");
      const data = await getConversations();
      console.log("Loaded conversations:", data?.length || 0);
      setConversations(data || []);
      setError(null);
      return data; // Return data for chaining
    } catch (err) {
      const errorMsg = `Error loading conversations: ${err.toString()}`;
      console.error(errorMsg);
      setError(errorMsg);
      return []; // Return empty array on error
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Function to load a specific conversation with its messages
  const loadConversation = useCallback(async (id) => {
    if (!id) return null;
    
    try {
      setLoading(true);
      console.log(`Loading conversation: ${id}`);
      const conversation = await getConversationById(id);
      setCurrentConversation(conversation);
      
      // Load messages for this conversation
      console.log(`Loading messages for conversation: ${id}`);
      const conversationMessages = await getMessages(id);
      setMessages(conversationMessages || []);
      
      setError(null);
      return conversation;
    } catch (err) {
      const errorMsg = `Error loading conversation ${id}: ${err.toString()}`;
      console.error(errorMsg);
      setError(errorMsg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Create a new conversation
  const newConversation = useCallback(async (name = 'New Conversation', systemMessage = 'You are a helpful assistant.') => {
    try {
      setLoading(true);
      console.log(`Creating new conversation: "${name}"`);
      const created = await createConversation({ name, system_message: systemMessage });
      
      if (!created) {
        console.error("Failed to create conversation: API returned null or undefined");
        throw new Error("Failed to create conversation");
      }
      
      console.log("Conversation created:", created);
      
      // Add to conversations list and set as current
      setConversations(prev => [created, ...prev]);
      setCurrentConversation(created);
      setMessages([]);
      
      return created;
    } catch (err) {
      const errorMsg = `Error creating conversation: ${err.toString()}`;
      console.error(errorMsg);
      setError(errorMsg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Send a message in the current conversation
  const sendUserMessage = useCallback(async (content, parentId = null) => {
    if (!currentConversation?.id) {
      setError('No conversation selected');
      return null;
    }
    
    try {
      const userMessage = await sendMessage(
        currentConversation.id, 
        content,
        parentId || currentConversation.current_node_id
      );
      
      // Add to messages
      setMessages(prev => [...prev, userMessage]);
      
      return userMessage;
    } catch (err) {
      setError(err.toString());
      console.error('Error sending message:', err);
      return null;
    }
  }, [currentConversation]);
  
  // Stream a chat response
  const streamResponse = useCallback((content, userMessageId = null) => {
    if (!currentConversation?.id) {
      setError('No conversation selected');
      return;
    }
    
    // Cancel any existing streaming request
    if (streamingRef.current) {
      streamingRef.current.abort();
    }
    
    // Initialize a placeholder for the streaming message
    setStreamingMessage({
      id: 'streaming',
      role: 'assistant',
      content: '',
      is_streaming: true
    });
    
    // Set a timeout to show an error if nothing happens after a while
    const streamTimeout = setTimeout(() => {
      if (streamingRef.current) {
        // If we still have an active streaming request but no content after 15 seconds
        handleError('The AI service is taking too long to respond. This might be due to high demand or service issues.');
        if (streamingRef.current) {
          streamingRef.current.abort();
          streamingRef.current = null;
        }
      }
    }, 15000);
    
    // Handle incoming chunks
    const handleChunk = (chunk) => {
      // Clear the timeout since we got a response
      clearTimeout(streamTimeout);
      
      if (chunk.content) {
        setStreamingMessage(prev => ({
          ...prev,
          content: prev.content + chunk.content
        }));
      }
    };
    
    // Handle completion
    const handleComplete = (finalMessage) => {
      clearTimeout(streamTimeout);
      streamingRef.current = null;
      
      // Replace streaming message with the final message
      setStreamingMessage(null);
      
      // Add the final message to the messages array
      setMessages(prev => [...prev, finalMessage]);
      
      // Update current conversation state if needed
      setCurrentConversation(prev => ({
        ...prev,
        current_node_id: finalMessage.id
      }));
    };
    
    // Handle errors
    const handleError = (err) => {
      clearTimeout(streamTimeout);
      console.error('Streaming error:', err);
      streamingRef.current = null;
      
      // Show the error in the UI by converting the streaming message to an error message
      setStreamingMessage(prev => prev ? {
        ...prev,
        role: 'system',
        content: `Error: ${err}`,
        is_error: true
      } : null);
      
      // Set the global error state
      setError(err.toString());
      
      // After a delay, remove the error message
      setTimeout(() => {
        setStreamingMessage(null);
      }, 5000);
    };
    
    // Start streaming - pass the user message ID to avoid duplication
    try {
      streamingRef.current = streamChat(
        currentConversation.id,
        content,
        userMessageId || currentConversation.current_node_id,
        handleChunk,
        handleComplete,
        handleError
      );
    } catch (err) {
      handleError(err.toString());
    }
    
    // Return abort function
    return () => {
      clearTimeout(streamTimeout);
      if (streamingRef.current) {
        streamingRef.current.abort();
        streamingRef.current = null;
        setStreamingMessage(null);
      }
    };
  }, [currentConversation, streamChat]);
  
  // Navigate to a specific message in the conversation history
  const navigateHistory = useCallback(async (messageId) => {
    if (!currentConversation?.id || !messageId) return;
    
    try {
      await navigateToMessage(currentConversation.id, messageId);
      
      // Update current conversation with new current_node_id
      setCurrentConversation(prev => ({
        ...prev,
        current_node_id: messageId
      }));
      
      return true;
    } catch (err) {
      setError(err.toString());
      console.error('Error navigating to message:', err);
      return false;
    }
  }, [currentConversation]);
  
  // Update conversation details (name, system message)
  const updateCurrentConversation = useCallback(async (updates) => {
    if (!currentConversation?.id) return;
    
    try {
      const updated = await updateConversation(currentConversation.id, updates);
      
      // Update in state
      setCurrentConversation(updated);
      
      // Update in conversations list
      setConversations(prev => 
        prev.map(conv => conv.id === updated.id ? updated : conv)
      );
      
      return updated;
    } catch (err) {
      setError(err.toString());
      console.error('Error updating conversation:', err);
      return null;
    }
  }, [currentConversation]);
  
  // Delete a conversation
  const removeConversation = useCallback(async (id) => {
    if (!id) return false;
    
    try {
      await deleteConversation(id);
      
      // Remove from conversations list
      setConversations(prev => prev.filter(conv => conv.id !== id));
      
      // Clear current conversation if it was deleted
      if (currentConversation?.id === id) {
        setCurrentConversation(null);
        setMessages([]);
      }
      
      return true;
    } catch (err) {
      setError(err.toString());
      console.error('Error deleting conversation:', err);
      return false;
    }
  }, [currentConversation]);
  
  // Load initial conversation if ID is provided
  useEffect(() => {
    let mounted = true;
    
    const initialize = async () => {
      // Always load the conversation list first
      await loadConversations();
      
      if (initialConversationId && mounted) {
        await loadConversation(initialConversationId);
      }
    };
    
    initialize();
    
    return () => { mounted = false; };
  }, [initialConversationId, loadConversation, loadConversations]);
  
  // Helper to get a flat list of all messages including streaming
  const getAllMessages = useCallback(() => {
    return streamingMessage 
      ? [...messages, streamingMessage]
      : messages;
  }, [messages, streamingMessage]);
  
  return {
    conversations,
    currentConversation,
    messages: getAllMessages(),
    loading,
    error,
    loadConversations,
    loadConversation,
    newConversation,
    sendUserMessage,
    streamResponse,
    navigateHistory,
    updateCurrentConversation,
    removeConversation,
    isStreaming: !!streamingMessage
  };
};
