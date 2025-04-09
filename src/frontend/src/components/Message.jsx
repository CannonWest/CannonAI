import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { formatDate, formatTokenUsage } from '../utils/formatters';

// Simple component for code blocks - no syntax highlighting
const SimpleCodeBlock = ({ children, className }) => {
  // Extract language from className if available
  const language = className ? className.replace('language-', '') : '';
  return (
    <pre className={`code-block ${language ? `language-${language}` : ''}`}>
      <code>{children}</code>
    </pre>
  );
};

const Message = ({ message, onNavigate }) => {
  const [showDetails, setShowDetails] = useState(false);
  
  if (!message) return null;
  
  const { role, content, timestamp, token_usage, is_streaming } = message;
  
  // Determine message class based on role
  const messageClass = `message message-${role}`;
  
  // Get user-friendly role name
  const getRoleName = (role) => {
    switch (role) {
      case 'user': return 'You';
      case 'assistant': return 'AI';
      case 'system': return 'System';
      default: return role;
    }
  };
  
  // Render file attachments if present
  const renderAttachments = () => {
    if (!message.file_attachments || message.file_attachments.length === 0) {
      return null;
    }
    
    return (
      <div className="message-attachments">
        <h4>Attachments:</h4>
        <ul>
          {message.file_attachments.map(file => (
            <li key={file.id} className="attachment">
              <span className="attachment-name">{file.display_name || file.file_name}</span>
              <span className="attachment-type">{file.mime_type}</span>
              {file.token_count > 0 && 
                <span className="attachment-tokens">{file.token_count} tokens</span>
              }
            </li>
          ))}
        </ul>
      </div>
    );
  };
  
  // Show a pulsing indicator for streaming messages
  const streamingIndicator = is_streaming && (
    <div className="streaming-indicator">
      <span className="dot"></span>
      <span className="dot"></span>
      <span className="dot"></span>
    </div>
  );
  
  return (
    <div className={messageClass}>
      <div className="message-header">
        <span className="message-role">{getRoleName(role)}</span>
        {timestamp && (
          <span className="message-time" title={new Date(timestamp).toLocaleString()}>
            {formatDate(timestamp)}
          </span>
        )}
        {!is_streaming && message.id && (
          <button 
            className="message-navigate-btn" 
            onClick={() => onNavigate && onNavigate(message.id)}
            title="Navigate to this message"
          >
            →
          </button>
        )}
      </div>
      
      {renderAttachments()}
      
      {message.reasoning_steps && message.reasoning_steps.length > 0 && (
        <div className="reasoning-steps-summary">
          <h4>AI used {message.reasoning_steps.length} reasoning steps</h4>
        </div>
      )}
      
      <div className="message-content">
        <ReactMarkdown 
          components={{ 
            code: SimpleCodeBlock
          }}
        >
          {content || ''}
        </ReactMarkdown>
        
        {streamingIndicator}
      </div>
      
      {token_usage && (
        <div className="message-footer">
          <button 
            className="details-toggle" 
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? 'Hide Details' : 'Show Details'}
          </button>
          
          {showDetails && (
            <div className="message-details">
              <div className="token-usage">
                {formatTokenUsage(token_usage)}
              </div>
              {message.model_info && (
                <div className="model-info">
                  Model: {message.model_info.name || message.model_info.model}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Message;
