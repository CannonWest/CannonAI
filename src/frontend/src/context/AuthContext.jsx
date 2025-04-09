import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import { validateApiKey } from '../services/api';

const AuthContext = createContext();

// Store/retrieve API key from localStorage
const API_KEY_STORAGE_KEY = 'cannon_ai_api_key';

export const AuthProvider = ({ children }) => {
  const [apiKey, setApiKey] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState(null);
  
  // Load API key from localStorage on mount
  useEffect(() => {
    const savedApiKey = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (savedApiKey) {
      setApiKey(savedApiKey);
      validateSavedApiKey(savedApiKey);
    }
  }, []);
  
  // Validate a saved API key without showing errors
  const validateSavedApiKey = async (key) => {
    try {
      setVerifying(true);
      const isValid = await validateApiKey(key);
      setIsAuthenticated(isValid);
    } catch (err) {
      console.error('Error validating saved API key:', err);
      setIsAuthenticated(false);
    } finally {
      setVerifying(false);
    }
  };
  
  // Set and validate a new API key
  const login = useCallback(async (key) => {
    if (!key) {
      setError('API key is required');
      return false;
    }
    
    try {
      setVerifying(true);
      setError(null);
      
      const isValid = await validateApiKey(key);
      
      if (isValid) {
        // Save to state and localStorage
        setApiKey(key);
        setIsAuthenticated(true);
        localStorage.setItem(API_KEY_STORAGE_KEY, key);
        return true;
      } else {
        setError('Invalid API key');
        setIsAuthenticated(false);
        return false;
      }
    } catch (err) {
      setError(err.toString());
      setIsAuthenticated(false);
      return false;
    } finally {
      setVerifying(false);
    }
  }, []);
  
  // Clear API key and authentication state
  const logout = useCallback(() => {
    setApiKey('');
    setIsAuthenticated(false);
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  }, []);
  
  return (
    <AuthContext.Provider value={{ 
      apiKey, 
      isAuthenticated, 
      verifying,
      error,
      login,
      logout
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
