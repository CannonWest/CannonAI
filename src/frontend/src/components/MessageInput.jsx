import React, { useState, useRef, useEffect } from 'react';
import { estimateTokenCount } from '../utils/tokenCounter';

const MessageInput = ({ onSend, disabled, placeholder = "Type your message here..." }) => {
  const [message, setMessage] = useState('');
  const [tokenCount, setTokenCount] = useState(0);
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef(null);
  
  // Auto-resize textarea as content grows
  useEffect(() => {
    if (!textareaRef.current) return;
    
    // Reset height to auto to get the correct scrollHeight
    textareaRef.current.style.height = 'auto';
    // Set to scrollHeight to ensure all content is visible (with a max height)
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
  }, [message]);
  
  // Update token count when message changes
  useEffect(() => {
    setTokenCount(estimateTokenCount(message));
  }, [message]);
  
  const handleChange = (e) => {
    setMessage(e.target.value);
  };
  
  const handleKeyDown = (e) => {
    // Send message on Enter (but not if Shift is held or in IME composition)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };
  
  // Handle IME composition (for languages like Chinese, Japanese, Korean)
  const handleCompositionStart = () => setIsComposing(true);
  const handleCompositionEnd = () => setIsComposing(false);
  
  const handleSend = () => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage || disabled) return;
    
    onSend(trimmedMessage);
    setMessage('');
    
    // Focus back on textarea
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };
  
  return (
    <div className="cannon-message-input">
      <textarea 
        ref={textareaRef}
        className="cannon-message-textarea"
        value={message}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onCompositionStart={handleCompositionStart}
        onCompositionEnd={handleCompositionEnd}
        placeholder={placeholder}
        disabled={disabled}
        rows={1} // Start with one row, will auto-expand
      />
      
      <div className="cannon-input-controls">
        <div className="cannon-token-counter">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
            <line x1="9" y1="9" x2="9.01" y2="9"></line>
            <line x1="15" y1="9" x2="15.01" y2="9"></line>
          </svg>
          {tokenCount} tokens
        </div>
        
        <button 
          className="cannon-send-button"
          onClick={handleSend}
          disabled={!message.trim() || disabled}
        >
          {disabled ? (
            <span>Processing...</span>
          ) : (
            <>
              <span>Send</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </>
          )}
        </button>
      </div>
    </div>
  );
};

export default MessageInput;