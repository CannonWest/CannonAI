import React, { useRef, useEffect } from 'react';
import MessageInput from './MessageInput';

const TypingIndicator = () => (
  <div className="cannon-typing-indicator">
    <span></span>
    <span></span>
    <span></span>
  </div>
);

const ChatInterface = ({ conversationContext }) => {
  const { 
    currentConversation, 
    messages, 
    isStreaming, 
    sendMessage, 
    navigateToMessage 
  } = conversationContext || {};
  
  const messagesEndRef = useRef(null);
  
  // Auto-scroll to bottom when messages update or when streaming
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);
  
  const handleSendMessage = (content) => {
    if (sendMessage && content.trim()) {
      sendMessage(content);
    }
  };
  
  const handleNavigate = (messageId) => {
    if (navigateToMessage) {
      navigateToMessage(messageId);
    }
  };
  
  // Format timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };
  
  // If no conversation is selected, show empty state
  if (!currentConversation) {
    return (
      <div className="cannon-empty-state">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          <line x1="9" y1="10" x2="15" y2="10"></line>
          <line x1="12" y1="7" x2="12" y2="13"></line>
        </svg>
        <h2>No Conversation Selected</h2>
        <p>Select a conversation from the sidebar or create a new one to start chatting.</p>
      </div>
    );
  }
  
  return (
    <div className="cannon-chat-interface">
      <div className="cannon-messages-container">
        {(!messages || messages.length === 0) ? (
          <div className="cannon-empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <h3>New Conversation</h3>
            <p>Type a message below to start chatting with the AI assistant.</p>
          </div>
        ) : (
          <>
            {messages.map(message => (
              <div 
                key={message.id || `tmp-${Date.now()}-${Math.random()}`} 
                className={`cannon-message cannon-message-${message.role}`}
              >
                <div className="cannon-message-header">
                  <span className="cannon-message-role">
                    {message.role === 'user' ? 'You' : 
                     message.role === 'system' ? 'System' : 
                     message.role === 'assistant' ? 'AI Assistant' : 
                     'Unknown'}
                  </span>
                  <span className="cannon-message-time">
                    {formatTime(message.timestamp)}
                  </span>
                </div>
                <div className="cannon-message-content">
                  {message.content}
                </div>
                {message.token_usage && (
                  <div className="cannon-message-tokens">
                    {message.token_usage.total_tokens 
                      ? `Tokens: ${message.token_usage.total_tokens}` 
                      : ''}
                  </div>
                )}
              </div>
            ))}
            {isStreaming && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>
      
      <MessageInput 
        onSend={handleSendMessage} 
        disabled={isStreaming}
        placeholder={isStreaming ? "AI is responding..." : "Type your message here..."}
      />
    </div>
  );
};

export default ChatInterface;