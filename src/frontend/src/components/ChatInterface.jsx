import React, { useRef, useEffect } from 'react';
import MessageInput from './MessageInput';
import Message from './Message';
import TypingIndicator from './TypingIndicator';

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
  
  return (
    <div className="chat-interface">
      {!currentConversation ? (
        <div className="empty-state">
          <h2>No Conversation Selected</h2>
          <p>Select a conversation from the sidebar or create a new one to start chatting.</p>
        </div>
      ) : (
        <>
          <div className="messages-container">
            {(!messages || messages.length === 0) ? (
              <div className="empty-conversation">
                <h3>New Conversation</h3>
                <p>Send a message to start chatting with the AI.</p>
              </div>
            ) : (
              <>
                {messages.map(message => (
                  <Message 
                    key={message.id || `tmp-${Date.now()}-${Math.random()}`} 
                    message={message}
                    onNavigate={handleNavigate}
                  />
                ))}
                {isStreaming && <TypingIndicator />}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>
          
          <MessageInput 
            onSend={handleSendMessage} 
            disabled={isStreaming}
            placeholder={isStreaming ? "AI is responding..." : "Type your message here..."}
          />
        </>
      )}
    </div>
  );
};

export default ChatInterface;
