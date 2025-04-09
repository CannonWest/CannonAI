import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { getSettings, saveSettings, resetSettings } from '../services/api';

const SettingsContext = createContext();

export const SettingsProvider = ({ children }) => {
  const [settings, setSettings] = useState({
    model: 'gpt-4o',
    temperature: 0.7,
    max_output_tokens: 1024,
    top_p: 1.0,
    stream: true,
    text: { format: { type: 'text' } },
    reasoning: { effort: 'medium' },
    api_type: 'responses',
    store: true,
    seed: null
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Load settings from API
  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getSettings();
      setSettings(data);
      setError(null);
    } catch (err) {
      setError(err.toString());
      console.error('Error loading settings:', err);
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Save settings to API
  const updateSettings = useCallback(async (newSettings) => {
    try {
      setLoading(true);
      
      // Merge with current settings
      const updatedSettings = { ...settings, ...newSettings };
      
      // Save to API
      const saved = await saveSettings(updatedSettings);
      
      // Update local state
      setSettings(saved);
      setError(null);
      
      return saved;
    } catch (err) {
      setError(err.toString());
      console.error('Error saving settings:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, [settings]);
  
  // Update a single setting
  const updateSetting = useCallback(async (key, value) => {
    return updateSettings({ [key]: value });
  }, [updateSettings]);
  
  // Reset settings to defaults
  const resetToDefaults = useCallback(async () => {
    try {
      setLoading(true);
      const defaults = await resetSettings();
      setSettings(defaults);
      setError(null);
      return defaults;
    } catch (err) {
      setError(err.toString());
      console.error('Error resetting settings:', err);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  
  // Load settings on mount
  useEffect(() => {
    loadSettings();
  }, [loadSettings]);
  
  // Helper to check if a model is a reasoning model
  const isReasoningModel = useCallback((model) => {
    const reasoningModels = [
      'o1', 'o1-mini', 'o3-mini', 'deepseek-reasoner',
      'o1-2024-12-17', 'o1-preview-2024-09-12', 'o3-mini-2025-01-31'
    ];
    return reasoningModels.includes(model);
  }, []);
  
  // Create context value
  const contextValue = {
    settings,
    loading,
    error,
    updateSettings,
    updateSetting,
    resetToDefaults,
    loadSettings,
    isReasoningModel
  };

  return (
    <SettingsContext.Provider value={contextValue}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => useContext(SettingsContext);
