import { create } from 'zustand';
import { fetchConversations, createConversation, deleteConversation } from '../services/api';

export interface Conversation {
  id: number;
  title: string;
  model_provider: string;
  model_name: string;
  created_at: string;
  updated_at: string;
}

interface ConversationState {
  conversations: Conversation[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  fetchConversations: () => Promise<void>;
  createConversation: (title: string, model_provider: string, model_name: string) => Promise<Conversation>;
  deleteConversation: (id: number) => Promise<void>;
  setConversations: (conversations: Conversation[]) => void;
}

const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  isLoading: false,
  error: null,
  
  fetchConversations: async () => {
    set({ isLoading: true, error: null });
    try {
      // TODO: Uncomment when API is available
      // const conversations = await fetchConversations();
      // set({ conversations, isLoading: false });
      
      // Placeholder data until API is connected
      set({
        conversations: [
          {
            id: 1,
            title: 'First Conversation',
            model_provider: 'openai',
            model_name: 'gpt-3.5-turbo',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          },
          {
            id: 2,
            title: 'Second Conversation',
            model_provider: 'google',
            model_name: 'gemini-pro',
            created_at: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
            updated_at: new Date(Date.now() - 86400000).toISOString()
          }
        ],
        isLoading: false
      });
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
      set({ error: 'Failed to fetch conversations', isLoading: false });
    }
  },
  
  createConversation: async (title, model_provider, model_name) => {
    set({ isLoading: true, error: null });
    try {
      // TODO: Uncomment when API is available
      // const newConversation = await createConversation({
      //   title,
      //   model_provider,
      //   model_name
      // });
      // set(state => ({
      //   conversations: [newConversation, ...state.conversations],
      //   isLoading: false
      // }));
      // return newConversation;
      
      // Placeholder implementation until API is connected
      const newConversation: Conversation = {
        id: Math.floor(Math.random() * 10000),
        title,
        model_provider,
        model_name,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      
      set(state => ({
        conversations: [newConversation, ...state.conversations],
        isLoading: false
      }));
      
      return newConversation;
    } catch (error) {
      console.error('Failed to create conversation:', error);
      set({ error: 'Failed to create conversation', isLoading: false });
      throw error;
    }
  },
  
  deleteConversation: async (id) => {
    set({ isLoading: true, error: null });
    try {
      // TODO: Uncomment when API is available
      // await deleteConversation(id);
      
      // Update state
      set(state => ({
        conversations: state.conversations.filter(conv => conv.id !== id),
        isLoading: false
      }));
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      set({ error: 'Failed to delete conversation', isLoading: false });
      throw error;
    }
  },
  
  setConversations: (conversations) => {
    set({ conversations });
  }
}));

export default useConversationStore;
