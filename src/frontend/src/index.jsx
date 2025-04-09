import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { SettingsProvider } from './context/SettingsContext';
import { ConversationProvider } from './context/ConversationContext';
import { ToastProvider } from './context/ToastContext';
import './styles.css';

// Create root
const root = ReactDOM.createRoot(document.getElementById('root'));

// Render app with context providers
root.render(
  <React.StrictMode>
    <AuthProvider>
      <SettingsProvider>
        <ConversationProvider>
          <ToastProvider>
            <App />
          </ToastProvider>
        </ConversationProvider>
      </SettingsProvider>
    </AuthProvider>
  </React.StrictMode>
);
