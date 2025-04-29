import axios from 'axios';

// Create axios instance with base URL
const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// API interfaces
export interface Conversation {
  id: number;
  title: string;
  model_provider: string;
  model_name: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationCreate {
  title: string;
  model_provider: string;
  model_name: string;
  settings?: {
    temperature?: number;
    max_tokens?: number;
    [key: string]: any;
  };
}

export interface Message {
  id: number;
  role: string;
  content: string;
  created_at: string;
}

export interface MessageCreate {
  content: string;
}

// Conversation endpoints
export const fetchConversations = async (): Promise<Conversation[]> => {
  const response = await api.get('/conversations');
  return response.data;
};

export const fetchConversation = async (id: string): Promise<Conversation> => {
  const response = await api.get(`/conversations/${id}`);
  return response.data;
};

export const getDefaultConversation = async (): Promise<Conversation> => {
  const response = await api.get('/conversations/default');
  return response.data;
};

export const createConversation = async (data: ConversationCreate): Promise<Conversation> => {
  const response = await api.post('/conversations', data);
  return response.data;
};

export const updateConversation = async (id: string, data: Partial<ConversationCreate>): Promise<Conversation> => {
  const response = await api.put(`/conversations/${id}`, data);
  return response.data;
};

export const deleteConversation = async (id: number): Promise<void> => {
  await api.delete(`/conversations/${id}`);
};

// Message endpoints
export const fetchMessages = async (conversationId: string): Promise<Message[]> => {
  const response = await api.get(`/conversations/${conversationId}/messages`);
  return response.data;
};

export const sendMessage = async (conversationId: string, content: string): Promise<Message> => {
  const response = await api.post(`/conversations/${conversationId}/messages`, { content });
  return response.data;
};

// Provider endpoints
export const fetchProviders = async (): Promise<string[]> => {
  const response = await api.get('/providers');
  return response.data;
};

export const fetchProviderModels = async (provider: string): Promise<string[]> => {
  const response = await api.get(`/providers/${provider}/models`);
  return response.data;
};

// Settings
export const saveSettings = async (settings: any): Promise<any> => {
    const response = await api.post('/settings', settings);
  return response.data;
};

// Error handler
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

export default api;
