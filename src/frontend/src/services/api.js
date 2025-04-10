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
export const streamChat = async (conversationId, content, parentId = null, onChunk, onComplete, onError) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  if (!content) throw new Error('Message content is required');
  
  try {
    // Send the content directly to the streaming endpoint without creating a user message first
    const response = await apiClient.post(
      `/conversations/${conversationId}/stream`,
      {
        content: content,  // Include the content directly
        parent_id: parentId // Use parentId if provided
      },
      {
        responseType: 'stream',
        onDownloadProgress: (progressEvent) => {
          const chunk = progressEvent.currentTarget.response;
          if (chunk) {
            try {
              const data = JSON.parse(chunk);
              onChunk(data);
            } catch (e) {
              // Ignore parsing errors for partial chunks
            }
          }
        }
      }
    );
    
    // Handle completion
    if (onComplete) {
      onComplete(response.data);
    }
    
    return response.data;
  } catch (error) {
    if (onError) {
      onError(formatError(error));
    } else {
      throw error;
    }
  }
};

// Streaming chat - WebSocket version for more efficient streaming
export const streamChatWebSocket = (conversationId, content, parentId = null, onChunk, onComplete, onError) => {
  if (!conversationId) throw new Error('Conversation ID is required');
  if (!content) throw new Error('Message content is required');
  
  // Create WebSocket connection
  const ws = new WebSocket(`ws://localhost:8000/ws/chat/${conversationId}`);
  
  // Track connection state
  let isConnected = false;
  let isClosedByClient = false;
  
  // Create abort controller for client-side abort
  const controller = {
    abort: () => {
      isClosedByClient = true;
      ws.close();
    }
  };
  
  ws.onopen = () => {
    isConnected = true;
    
    // Send the initial message
    ws.send(JSON.stringify({
      content,
      parent_id: parentId
    }));
  };
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      
      if (data.error) {
        if (onError) onError(data.error);
        return;
      }
      
      // Handle different event types
      if (data.type === 'assistant_message_delta') {
        if (onChunk) onChunk(data);
      } else if (data.type === 'reasoning_step') {
        if (onChunk) onChunk(data);
      } else if (data.type === 'assistant_message_complete' || data.type === 'assistant_message_saved') {
        if (onComplete) onComplete(data.message || data);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
      if (onError) onError('Error parsing response');
    }
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    if (onError) onError('WebSocket error: ' + (error.message || 'Unknown error'));
  };
  
  ws.onclose = () => {
    isConnected = false;
    if (!isClosedByClient) {
      // Only trigger error if not closed by the client intentionally
      if (onError) onError('WebSocket connection closed unexpectedly');
    }
  };
  
  // Return the controller to allow aborting
  return controller;
};

export default apiClient;
