import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { formatTokenUsage } from '../utils/formatters';

const Message = ({ message, onNavigate }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const { role, content, reasoning, token_usage, timestamp, id } = message || {};
  
  if (!message) return null;
  
  const formattedTime = timestamp ? new Date(timestamp).toLocaleTimeString() : '';
  
  // Determine message class based on role
  const messageClass = `message message-${role || 'user'}`;
  
  // Format the display name based on role
  const displayName = role === 'user' ? 'You' : 
                      role === 'system' ? 'System' : 
                      role === 'assistant' ? 'AI Assistant' : 
                      'Unknown';
  
  // Custom renderer for code blocks in markdown
  const renderers = {
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      const language = match ? match[1] : '';
      
      return !inline && language ? (
        <div className="code-block-wrapper">
          <div className="code-block-header">
            <span className="code-language">{language}</span>
            <button 
              className="copy-button"
              onClick={() => {
                navigator.clipboard.writeText(String(children).replace(/\n$/, ''));
              }}
            >
              Copy
            </button>
          </div>
          <SyntaxHighlighter
            language={language}
            PreTag="div"
            style={{
              backgroundColor: '#282a36',
              padding: '1rem',
              borderRadius: '0 0 4px 4px',
              overflow: 'auto'
            }}
            {...props}
          >
            {String(children).replace(/\n$/, '')}
          </SyntaxHighlighter>
        </div>
      ) : (
        <code className={className} {...props}>
          {children}
        </code>
      );
    }
  };
  
  // Handle reasoning toggle
  const toggleReasoning = () => {
    setIsExpanded(!isExpanded);
  };
  
  return (
    <div className={messageClass} id={`message-${id}`}>
      <div className="message-header">
        <span className="message-name">{displayName}</span>
        <span className="message-time">{formattedTime}</span>
      </div>
      
      <div className="message-content">
        {reasoning && (
          <div className="message-reasoning">
            <button 
              className="reasoning-toggle" 
              onClick={toggleReasoning}
            >
              {isExpanded ? 'Hide Reasoning' : 'Show Reasoning'}
            </button>
            
            {isExpanded && (
              <div className="reasoning-content">
                <ReactMarkdown components={renderers}>
                  {reasoning}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}
        
        <ReactMarkdown components={renderers}>
          {content || ''}
        </ReactMarkdown>
        
        {token_usage && (
          <div className="message-tokens">
            {formatTokenUsage(token_usage)}
          </div>
        )}
      </div>
    </div>
  );
};

export default Message;
