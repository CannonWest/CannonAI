import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { SettingsProvider } from './context/SettingsContext';
import { ToastProvider } from './context/ToastContext';
import { ConversationProvider } from './context/ConversationContext';
import './styles.css';

const root = createRoot(document.getElementById('root'));

root.render(
  <React.StrictMode>
    <ToastProvider>
      <AuthProvider>
        <SettingsProvider>
          <ConversationProvider>
            <App />
          </ConversationProvider>
        </SettingsProvider>
      </AuthProvider>
    </ToastProvider>
  </React.StrictMode>
);
