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
    // Set to scrollHeight to ensure all content is visible
    textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
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
  
  const handlePaste = (e) => {
    // Handle file paste
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      // TODO: Implement file attachment handling
      console.log('File pasted:', e.clipboardData.files);
      e.preventDefault();
    }
  };
  
  return (
    <div className="message-input">
      <textarea 
        ref={textareaRef}
        value={message}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onCompositionStart={handleCompositionStart}
        onCompositionEnd={handleCompositionEnd}
        onPaste={handlePaste}
        placeholder={placeholder}
        disabled={disabled}
        rows={1} // Start with one row, will auto-expand
        className={disabled ? 'disabled' : ''}
      />
      
      <div className="input-controls">
        <div className="token-counter" title="Estimated token count">
          {tokenCount} tokens
        </div>
        
        <button 
          className="send-button"
          onClick={handleSend}
          disabled={!message.trim() || disabled}
        >
          Send
        </button>
      </div>
    </div>
  );
};

export default MessageInput;
