// API service for making requests to the backend

import axios from 'axios';
import { formatError } from '../utils/formatters';

// Update the API_BASE_URL to ensure it points to the correct backend endpoint
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? '/api' 
  : 'http://localhost:8000/api'; // Use absolute URL in development

// Create axios instance with common configuration
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000, // 30 seconds
});

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => {
    // Log successful responses in development
    if (process.env.NODE_ENV !== 'production') {
      console.log(`API Success [${response.config.method} ${response.config.url}]:`, 
        response.status, response.data ? (Array.isArray(response.data) ? `(${response.data.length} items)` : 'data') : 'no data');
    }
    return response;
  },
  (error) => {
    console.error('API Error:', error.response?.status || 'Network Error', 
      error.response?.data || error.message, 
      'URL:', error.config?.url);
    return Promise.reject(formatError(error));
  }
);

// Intercept requests to include auth header
apiClient.interceptors.request.use(config => {
  // Log outgoing requests in development
  if (process.env.NODE_ENV !== 'production') {
    console.log(`API Request [${config.method}]:`, config.url, config.params ? config.params : '');
  }
  
  const apiKey = localStorage.getItem('cannon_ai_api_key');
  if (apiKey) {
    config.headers['Authorization'] = `Bearer ${apiKey}`;
  }
  return config;
});

// Conversations endpoints
export const getConversations = async (skip = 0, limit = 100) => {
  const response = await apiClient.get('/conversations', {
    params: { skip, limit }
  });
  return response.data;
};

export const getConversationById = async (id) => {
  if (!id) throw new Error('Conversation ID is required');
  const response = await apiClient.get(`/conversations/${id}`);
  return response.data;
};

export const createConversation = async (data = { name: 'New Conversation' }) => {
  const response = await apiClient.post('/conversations', data);
  return response.data;
};

export const updateConversation = async (id, data) => {
  if (!id) throw new Error('Conversation ID is required');
  const response = await apiClient.put(`/conversations/${id}`, data);
  return response.data;
};

export const deleteConversation = async (id) => {
  if (!id) throw new Error('Conversation ID is required');
  const response = await apiClient.delete(`/conversations/${id}`);
  return response.data;
};

export const duplicateConversation = async (id, newName) => {
  if (!id) throw new Error('Conversation ID is required');
  const response = await apiClient.post(`/conversations/${id}/duplicate`, { new_name: newName });
  return response.data;
};

// Messages endpoints
export const sendMessage = async (conversationId, content, parentId = null) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  if (!content) throw new Error('Message content is required');
  
  const response = await apiClient.post(`/conversations/${conversationId}/messages`, {
    content,
    parent_id: parentId
  });
  
  return response.data;
};

export const getMessages = async (conversationId) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  
  const response = await apiClient.get(`/conversations/${conversationId}/messages`);
  return response.data;
};

export const navigateToMessage = async (conversationId, messageId) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  if (!messageId) throw new Error('Message ID is required');
  
  const response = await apiClient.post(`/conversations/${conversationId}/navigate`, {
    message_id: messageId
  });
  
  return response.data;
};

// Settings endpoints
export const saveSettings = async (settings) => {
  const response = await apiClient.post('/settings', settings);
  return response.data;
};

export const getSettings = async () => {
  const response = await apiClient.get('/settings');
  return response.data;
};

export const resetSettings = async () => {
  const response = await apiClient.post('/settings/reset');
  return response.data;
};

// Authentication
export const validateApiKey = async (apiKey) => {
  try {
    const response = await apiClient.post('/validate-api-key', { api_key: apiKey });
    return response.data.valid;
  } catch (error) {
    console.error('API key validation error:', error);
    return false;
  }
};

// Streaming chat
export const streamChat = (conversationId, content, parentId = null, onChunk, onComplete, onError) => {
  // Just call the WebSocket implementation which is already defined
  return streamChatWebSocket(conversationId, content, parentId, onChunk, onComplete, onError);
};

export const streamChatWebSocket = (conversationId, content, parentId = null, onChunk, onComplete, onError) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  if (!content) throw new Error('Message content is required');
  
  // Fix the WebSocket URL construction for production vs development
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsBaseUrl = process.env.NODE_ENV === 'production' 
    ? `${protocol}//${window.location.host}/ws` 
    : 'ws://localhost:8000/ws';
  
  // Create WebSocket connection
  const ws = new WebSocket(`${wsBaseUrl}/chat/${conversationId}`);
  
  // Track connection state
  let isConnected = false;
  let isClosedByClient = false;
  let hasReceivedResponse = false;
  let connectionTimeout = null;
  
  // Set connection timeout
  connectionTimeout = setTimeout(() => {
    if (!isConnected) {
      if (onError) onError('WebSocket connection timeout. Please try again.');
      ws.close();
    }
  }, 10000); // 10 second timeout
  
  // Create abort controller for client-side abort
  const controller = {
    abort: () => {
      isClosedByClient = true;
      clearTimeout(connectionTimeout);
      ws.close();
    }
  };
  
  ws.onopen = () => {
    isConnected = true;
    clearTimeout(connectionTimeout);
    
    // Send the initial message
    ws.send(JSON.stringify({
      content,
      parent_id: parentId
    }));
    
    // Set response timeout
    setTimeout(() => {
      if (!hasReceivedResponse && isConnected) {
        if (onError) onError('No response received from AI service. Please check your API key and try again.');
        controller.abort();
      }
    }, 15000); // 15 second timeout for initial response
  };
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      hasReceivedResponse = true;
      
      if (data.error) {
        if (onError) onError(data.error);
        return;
      }
      
      // Handle warning messages (like duplicate messages)
      if (data.type === 'warning') {
        console.warn('WebSocket warning:', data.message);
        // We might want to display this to the user depending on the warning
        return;
      }
      
      // Handle different event types
      if (data.type === 'content' || data.type === 'assistant_message_delta') {
        if (onChunk) onChunk(data);
      } else if (data.type === 'reasoning_step' || data.type === 'response.thinking_step') {
        if (onChunk) onChunk(data);
      } else if (data.type === 'end' || data.type === 'assistant_message_complete' || 
                data.type === 'assistant_message_saved' || data.type === 'response.completed') {
        if (onComplete) onComplete(data.message || data);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      if (onError) onError('Error parsing response from AI service');
    }
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    if (onError) {
      // Provide more helpful error message based on common issues
      if (!navigator.onLine) {
        onError('Network connection lost. Please check your internet connection.');
      } else if (!isConnected) {
        onError('Could not connect to the AI service. Server may be unavailable.');
      } else {
        onError('Error communicating with AI service: ' + (error.message || 'Unknown error'));
      }
    }
  };
  
  ws.onclose = (event) => {
    clearTimeout(connectionTimeout);
    isConnected = false;
    
    if (!isClosedByClient && !hasReceivedResponse) {
      // Only trigger error if not closed by the client and no response received
      if (onError) {
        if (event.code === 1000) {
          // Normal closure, no response
          onError('AI service did not respond. Please try again.');
        } else if (event.code === 1008 || event.code === 1011) {
          // Policy violation or internal error
          onError('AI service error: ' + (event.reason || 'Server error'));
        } else {
          onError('Connection to AI service closed unexpectedly. Please try again.');
        }
      }
    }
  };
  
  // Return the controller to allow aborting
  return controller;
};

export default apiClient;
