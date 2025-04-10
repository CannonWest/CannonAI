import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useSettings } from '../context/SettingsContext';
import './Settings.css'; // We'll create a separate CSS file for settings

const Settings = ({ onClose }) => {
  const { apiKey, login, logout } = useAuth();
  const { settings, updateSettings, resetToDefaults, isReasoningModel } = useSettings();
  
  // Form state
  const [formValues, setFormValues] = useState({...settings});
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  
  // Update form when settings change
  useEffect(() => {
    setFormValues({...settings});
  }, [settings]);
  
  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormValues(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };
  
  const handleSliderChange = (e) => {
    const { name, value } = e.target;
    setFormValues(prev => ({
      ...prev,
      [name]: parseFloat(value)
    }));
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    
    try {
      await updateSettings(formValues);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (error) {
      console.error('Error saving settings:', error);
    } finally {
      setIsSaving(false);
    }
  };
  
  const handleReset = async () => {
    if (window.confirm('Reset all settings to defaults?')) {
      await resetToDefaults();
    }
  };
  
  const handleApiKeySubmit = async (e) => {
    e.preventDefault();
    if (apiKeyInput.trim()) {
      const success = await login(apiKeyInput.trim());
      if (success) {
        setApiKeyInput('');
      }
    }
  };
  
  // Get model options
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
    
    return Object.entries(models).map(([value, label]) => (
      <option key={value} value={value}>{label}</option>
    ));
  };
  
  return (
    <div className="cannon-settings">
      <div className="cannon-settings-header">
        <h2>Settings</h2>
        <button className="cannon-close-button" onClick={onClose}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      
      <div className="cannon-settings-content">
        <section className="cannon-settings-section">
          <h3>Authentication</h3>
          
          {apiKey ? (
            <div className="cannon-api-key-status">
              <p>API Key: {showApiKey ? apiKey : '••••••••••••••••••••••••••'}</p>
              <div className="cannon-key-actions">
                <button 
                  className="cannon-show-key-toggle"
                  onClick={() => setShowApiKey(!showApiKey)}
                >
                  {showApiKey ? 'Hide' : 'Show'}
                </button>
                <button className="cannon-remove-key" onClick={logout}>
                  Remove Key
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleApiKeySubmit} className="cannon-api-key-form">
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
        
        <form onSubmit={handleSubmit} className="cannon-settings-form">
          <section className="cannon-settings-section">
            <h3>Model Settings</h3>
            
            <div className="cannon-form-group">
              <label htmlFor="model">Model</label>
              <select 
                id="model"
                name="model"
                value={formValues.model}
                onChange={handleInputChange}
              >
                {getModelOptions()}
              </select>
            </div>
            
            <div className="cannon-form-group">
              <label htmlFor="temperature">
                Temperature: {formValues.temperature.toFixed(2)}
              </label>
              <input
                type="range"
                id="temperature"
                name="temperature"
                min="0"
                max="2"
                step="0.01"
                value={formValues.temperature}
                onChange={handleSliderChange}
              />
              <div className="cannon-range-labels">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>
            
            <div className="cannon-form-group">
              <label htmlFor="top_p">
                Top P: {formValues.top_p.toFixed(2)}
              </label>
              <input
                type="range"
                id="top_p"
                name="top_p"
                min="0"
                max="1"
                step="0.01"
                value={formValues.top_p}
                onChange={handleSliderChange}
              />
            </div>
            
            <div className="cannon-form-group">
              <label htmlFor="max_output_tokens">Max Output Tokens</label>
              <input
                type="number"
                id="max_output_tokens"
                name="max_output_tokens"
                min="64"
                max="32000"
                value={formValues.max_output_tokens}
                onChange={handleInputChange}
              />
            </div>
            
            {isReasoningModel(formValues.model) && (
              <div className="cannon-form-group">
                <label htmlFor="reasoning_effort">Reasoning Effort</label>
                <select
                  id="reasoning_effort"
                  name="reasoning"
                  value={JSON.stringify(formValues.reasoning || { effort: 'medium' })}
                  onChange={(e) => {
                    setFormValues(prev => ({
                      ...prev,
                      reasoning: JSON.parse(e.target.value)
                    }));
                  }}
                >
                  <option value='{"effort":"low"}'>Low</option>
                  <option value='{"effort":"medium"}'>Medium</option>
                  <option value='{"effort":"high"}'>High</option>
                </select>
              </div>
            )}
            
            <div className="cannon-form-group cannon-checkbox">
              <input
                type="checkbox"
                id="stream"
                name="stream"
                checked={formValues.stream}
                onChange={handleInputChange}
              />
              <label htmlFor="stream">Enable streaming responses</label>
            </div>
          </section>
          
          <section className="cannon-settings-section">
            <h3>Advanced Settings</h3>
            
            <div className="cannon-form-group">
              <label htmlFor="api_type">API Type</label>
              <select
                id="api_type"
                name="api_type"
                value={formValues.api_type}
                onChange={handleInputChange}
              >
                <option value="responses">Responses API</option>
                <option value="chat_completions">Chat Completions API</option>
              </select>
            </div>
            
            <div className="cannon-form-group">
              <label htmlFor="seed">Random Seed (optional)</label>
              <input
                type="number"
                id="seed"
                name="seed"
                placeholder="Random if empty"
                value={formValues.seed ?? ''}
                onChange={(e) => {
                  const value = e.target.value.trim();
                  setFormValues(prev => ({
                    ...prev,
                    seed: value === '' ? null : parseInt(value, 10)
                  }));
                }}
              />
            </div>
            
            <div className="cannon-form-group cannon-checkbox">
              <input
                type="checkbox"
                id="store"
                name="store"
                checked={formValues.store}
                onChange={handleInputChange}
              />
              <label htmlFor="store">Store completions on OpenAI servers</label>
            </div>
          </section>
          
          <div className="cannon-settings-actions">
            {saveSuccess && <span className="cannon-save-success">Settings saved!</span>}
            <button type="button" className="cannon-reset-btn" onClick={handleReset}>
              Reset to Defaults
            </button>
            <button type="submit" className="cannon-save-btn" disabled={isSaving}>
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Settings;