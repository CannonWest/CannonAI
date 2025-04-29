import { useState, useEffect } from 'react';
import { FiSave } from 'react-icons/fi';
import useSettingsStore from '../store/useSettingsStore';

const SettingsPage = () => {
  const { 
    settings, 
    isLoading, 
    error, 
    updateSettings, 
    updateApiKey, 
    saveSettings 
  } = useSettingsStore();
  
  const [saveMessage, setSaveMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

  // Update error message if store has an error
  useEffect(() => {
    if (error) {
      setSaveMessage({
        type: 'error',
        text: error
      });
    }
  }, [error]);

  const handleSettingChange = (setting: string, value: string) => {
    updateSettings({ [setting]: value });
  };

  const handleApiKeyChange = (provider: string, value: string) => {
    updateApiKey(provider, value);
  };

  const handleSaveSettings = async () => {
    setSaveMessage(null);
    
    try {
      await saveSettings();
      
      setSaveMessage({
        type: 'success',
        text: 'Settings saved successfully!'
      });
    } catch (e) {
      // Error is already handled by the store
    }
  };

  return (
    <div className="max-w-4xl mx-auto pt-6 pb-12">
      <h1 className="text-2xl font-bold text-gray-800 dark:text-white mb-6">Settings</h1>
      
      <div className="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden">
        {/* Appearance */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-medium text-gray-800 dark:text-white mb-4">Appearance</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Theme
              </label>
              <select
                value={settings.theme}
                onChange={(e) => handleSettingChange('theme', e.target.value)}
                className="w-full md:w-1/3 p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="system">System Preference</option>
              </select>
            </div>
          </div>
        </div>
        
        {/* Defaults */}
        <div className="p-6 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-medium text-gray-800 dark:text-white mb-4">Default Settings</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Default Provider
              </label>
              <select
                value={settings.defaultProvider}
                onChange={(e) => handleSettingChange('defaultProvider', e.target.value)}
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              >
                <option value="openai">OpenAI</option>
                <option value="google">Google</option>
                {/* TODO: Add more providers */}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Default Model
              </label>
              <select
                value={settings.defaultModel}
                onChange={(e) => handleSettingChange('defaultModel', e.target.value)}
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              >
                <option value="gpt-4">GPT-4</option>
                <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                {/* TODO: Dynamically load models based on provider */}
              </select>
            </div>
          </div>
        </div>
        
        {/* API Keys */}
        <div className="p-6">
          <h2 className="text-lg font-medium text-gray-800 dark:text-white mb-4">API Keys</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                OpenAI API Key
              </label>
              <input
                type="password"
                value={settings.apiKeys.openai || ''}
                onChange={(e) => handleApiKeyChange('openai', e.target.value)}
                placeholder="sk-..."
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Google API Key
              </label>
              <input
                type="password"
                value={settings.apiKeys.google || ''}
                onChange={(e) => handleApiKeyChange('google', e.target.value)}
                placeholder="Enter your Google API key"
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              />
            </div>
          </div>
        </div>
        
        {/* Save button */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-700 flex items-center justify-between">
          {saveMessage && (
            <span className={`text-sm ${saveMessage.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              {saveMessage.text}
            </span>
          )}
          
          <button
            onClick={handleSaveSettings}
            disabled={isLoading}
            className={`ml-auto flex items-center gap-2 px-4 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 ${
              isLoading ? 'opacity-70 cursor-not-allowed' : ''
            }`}
          >
            <FiSave />
            {isLoading ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
