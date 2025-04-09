import React, { useState } from 'react';
import { useSettings } from '../context/SettingsContext';
import { useAuth } from '../context/AuthContext';

const Settings = () => {
  const { settings, updateSettings, updateSetting, resetToDefaults, isReasoningModel } = useSettings();
  const { apiKey, login, logout } = useAuth();
  
  // Local state for API key input
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  
  // Handle form submission
  const handleSubmit = (e) => {
    e.preventDefault();
    updateSettings(settings);
  };
  
  // Handle API key submission
  const handleApiKeySubmit = async (e) => {
    e.preventDefault();
    if (apiKeyInput.trim()) {
      const success = await login(apiKeyInput.trim());
      if (success) {
        setApiKeyInput('');
      }
    }
  };
  
  // Handle slider change
  const handleSliderChange = (e, key, min = 0, max = 1, step = 0.01) => {
    const value = parseFloat(e.target.value);
    // Ensure value is within bounds and properly formatted
    const normalizedValue = Math.max(min, Math.min(max, value));
    updateSetting(key, normalizedValue);
  };
  
  // Get a list of models for the dropdown
  const getModelOptions = () => {
    const models = {
      'gpt-4o': 'GPT-4o',
      'gpt-4o-mini': 'GPT-4o Mini',
      'gpt-4.5-preview': 'GPT-4.5 Turbo (Preview)',
      'gpt-4-turbo': 'GPT-4 Turbo',
      'gpt-3.5-turbo': 'GPT-3.5 Turbo',
      'o1': 'o1 (Reasoning)',
      'o1-mini': 'o1-mini (Reasoning)',
      'o3-mini': 'o3-mini (Reasoning)',
      'deepseek-chat': 'DeepSeek Chat',
      'deepseek-reasoner': 'DeepSeek Reasoner'
    };
    
    // Create option elements
    return Object.entries(models).map(([value, label]) => (
      <option key={value} value={value}>{label}</option>
    ));
  };
  
  return (
    <div className="settings">
      <h2>Settings</h2>
      
      <section className="settings-section auth-section">
        <h3>Authentication</h3>
        
        {apiKey ? (
          <div className="api-key-status">
            <p>API Key: {showApiKey ? apiKey : '••••••••••••••••••••••••••'}</p>
            <div className="key-actions">
              <button 
                className="show-key-toggle"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? 'Hide' : 'Show'}
              </button>
              <button className="remove-key" onClick={logout}>
                Remove Key
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleApiKeySubmit} className="api-key-form">
            <input
              type="password"
              placeholder="Enter OpenAI API Key"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
            />
            <button type="submit" disabled={!apiKeyInput.trim()}>
              Save API Key
            </button>
          </form>
        )}
      </section>
      
      <form onSubmit={handleSubmit} className="settings-form">
        <section className="settings-section">
          <h3>Model Settings</h3>
          
          <div className="form-group">
            <label htmlFor="model">Model</label>
            <select 
              id="model"
              value={settings.model}
              onChange={(e) => updateSetting('model', e.target.value)}
            >
              {getModelOptions()}
            </select>
          </div>
          
          <div className="form-group">
            <label htmlFor="temperature">
              Temperature: {settings.temperature.toFixed(2)}
            </label>
            <input
              type="range"
              id="temperature"
              min="0"
              max="2"
              step="0.01"
              value={settings.temperature}
              onChange={(e) => handleSliderChange(e, 'temperature', 0, 2)}
            />
            <div className="range-labels">
              <span>Precise</span>
              <span>Creative</span>
            </div>
          </div>
          
          <div className="form-group">
            <label htmlFor="top_p">
              Top P: {settings.top_p.toFixed(2)}
            </label>
            <input
              type="range"
              id="top_p"
              min="0"
              max="1"
              step="0.01"
              value={settings.top_p}
              onChange={(e) => handleSliderChange(e, 'top_p', 0, 1)}
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="max_output_tokens">Max Output Tokens</label>
            <input
              type="number"
              id="max_output_tokens"
              min="64"
              max="32000"
              value={settings.max_output_tokens}
              onChange={(e) => updateSetting('max_output_tokens', parseInt(e.target.value, 10))}
            />
          </div>
          
          {isReasoningModel(settings.model) && (
            <div className="form-group">
              <label htmlFor="reasoning_effort">Reasoning Effort</label>
              <select
                id="reasoning_effort"
                value={settings.reasoning?.effort || 'medium'}
                onChange={(e) => updateSetting('reasoning', { effort: e.target.value })}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
          )}
          
          <div className="form-group checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.stream}
                onChange={(e) => updateSetting('stream', e.target.checked)}
              />
              Enable streaming responses
            </label>
          </div>
        </section>
        
        <section className="settings-section">
          <h3>Advanced Settings</h3>
          
          <div className="form-group">
            <label htmlFor="api_type">API Type</label>
            <select
              id="api_type"
              value={settings.api_type}
              onChange={(e) => updateSetting('api_type', e.target.value)}
            >
              <option value="responses">Responses API</option>
              <option value="chat_completions">Chat Completions API</option>
            </select>
          </div>
          
          <div className="form-group">
            <label htmlFor="seed">Random Seed (optional)</label>
            <input
              type="number"
              id="seed"
              placeholder="Random if empty"
              value={settings.seed ?? ''}
              onChange={(e) => {
                const value = e.target.value.trim();
                updateSetting('seed', value === '' ? null : parseInt(value, 10));
              }}
            />
          </div>
          
          <div className="form-group checkbox">
            <label>
              <input
                type="checkbox"
                checked={settings.store}
                onChange={(e) => updateSetting('store', e.target.checked)}
              />
              Store completions on OpenAI servers
            </label>
          </div>
        </section>
        
        <div className="settings-actions">
          <button type="button" className="reset-btn" onClick={resetToDefaults}>
            Reset to Defaults
          </button>
          <button type="submit" className="save-btn">
            Save Settings
          </button>
        </div>
      </form>
    </div>
  );
};

export default Settings;
