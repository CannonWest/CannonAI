import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Settings {
  theme: 'light' | 'dark' | 'system';
  defaultProvider: string;
  defaultModel: string;
  apiKeys: {
    openai?: string;
    google?: string;
    [key: string]: string | undefined;
  };
}

interface SettingsState {
  settings: Settings;
  isLoading: boolean;
  error: string | null;
  
  // Actions
  updateSettings: (newSettings: Partial<Settings>) => void;
  updateApiKey: (provider: string, key: string) => void;
  saveSettings: () => Promise<void>;
}

const defaultSettings: Settings = {
  theme: 'system',
  defaultProvider: 'openai',
  defaultModel: 'gpt-3.5-turbo',
  apiKeys: {}
};

const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: defaultSettings,
      isLoading: false,
      error: null,
      
      updateSettings: (newSettings) => {
        set(state => ({
          settings: {
            ...state.settings,
            ...newSettings
          }
        }));
        
        // Apply theme immediately
        const { theme } = get().settings;
        if (theme === 'dark') {
          document.documentElement.classList.add('dark');
        } else if (theme === 'light') {
          document.documentElement.classList.remove('dark');
        } else {
          // System preference
          const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
          if (prefersDark) {
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
          }
        }
      },
      
      updateApiKey: (provider, key) => {
        set(state => ({
          settings: {
            ...state.settings,
            apiKeys: {
              ...state.settings.apiKeys,
              [provider]: key
            }
          }
        }));
      },
      
      saveSettings: async () => {
        set({ isLoading: true, error: null });
        try {
          // TODO: Implement actual API call if settings should be saved server-side
          // For now, we're just using local storage via the persist middleware
          
          // Simulate API call
          await new Promise(resolve => setTimeout(resolve, 500));
          
          set({ isLoading: false });
        } catch (error) {
          console.error('Failed to save settings:', error);
          set({ error: 'Failed to save settings', isLoading: false });
        }
      }
    }),
    {
      name: 'ai-chat-manager-settings'
    }
  )
);

export default useSettingsStore;
