/**
 * API service for communication with the Gemini Chat backend
 */

import axios from 'axios';

// Base API configuration
const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ----- Conversation Management -----

/**
 * Get a list of all conversations
 * @returns {Promise<Array>} List of conversations
 */
export const listConversations = async () => {
  const response = await api.get('/conversations');
  return response.data;
};

/**
 * Create a new conversation
 * @param {string} title - Title for the new conversation
 * @param {string} model - Optional model to use
 * @returns {Promise<Object>} New conversation data
 */
export const createConversation = async (title, model = null) => {
  const response = await api.post('/conversations', { title, model });
  return response.data;
};

/**
 * Load a conversation by ID
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<Object>} Conversation data with messages
 */
export const getConversation = async (conversationId) => {
  const response = await api.get(`/conversations/${conversationId}`);
  return response.data;
};

/**
 * Rename a conversation
 * @param {string} conversationId - Conversation ID
 * @param {string} title - New title
 * @returns {Promise<Object>} Updated conversation data
 */
export const renameConversation = async (conversationId, title) => {
  const response = await api.put(`/conversations/${conversationId}`, { title });
  return response.data;
};

/**
 * Delete a conversation
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<Object>} Status response
 */
export const deleteConversation = async (conversationId) => {
  const response = await api.delete(`/conversations/${conversationId}`);
  return response.data;
};

// ----- Messages -----

/**
 * Send a message to the AI (non-streaming)
 * @param {string} message - Message text
 * @param {string} conversationId - Conversation ID
 * @returns {Promise<Object>} AI response
 */
export const sendMessage = async (message, conversationId) => {
  const response = await api.post('/messages', { message, conversation_id: conversationId });
  return response.data;
};

// ----- Models -----

/**
 * Get a list of available models
 * @returns {Promise<Array>} List of models
 */
export const listModels = async () => {
  const response = await api.get('/models');
  return response.data;
};

/**
 * Select a model to use
 * @param {string} model - Model name
 * @returns {Promise<Object>} Status response
 */
export const selectModel = async (model) => {
  const response = await api.post('/models/select', { model });
  return response.data;
};

// ----- Configuration -----

/**
 * Get current configuration
 * @returns {Promise<Object>} Configuration data
 */
export const getConfig = async () => {
  const response = await api.get('/config');
  return response.data;
};

/**
 * Update configuration
 * @param {Object} configData - Configuration data to update
 * @returns {Promise<Object>} Status response
 */
export const updateConfig = async (configData) => {
  const response = await api.post('/config', configData);
  return response.data;
};

// ----- WebSocket Utilities -----

/**
 * Get WebSocket URL for streaming
 * @param {string} clientId - Client ID for the WebSocket connection
 * @returns {string} WebSocket URL
 */
export const getWebSocketUrl = (clientId) => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/ws/${clientId}`;
};

/**
 * Create a WebSocket message for streaming
 * @param {string} message - Message text
 * @param {string} conversationId - Conversation ID
 * @returns {Object} WebSocket message object
 */
export const createStreamMessage = (message, conversationId) => {
  return {
    action: 'send_message',
    data: {
      message,
      conversation_id: conversationId
    }
  };
};
