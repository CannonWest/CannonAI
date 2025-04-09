import React, { useEffect, useRef } from 'react';
import Message from './Message';
import MessageInput from './MessageInput';
import { useSettings } from '../context/SettingsContext';

const ChatInterface = ({ conversationContext }) => {
  const messagesEndRef = useRef(null);
  const { 
    currentConversation, 
    messages,
    isStreaming,
    sendUserMessage,
    streamResponse,
    navigateHistory
  } = conversationContext || {};
  
  const { settings } = useSettings();
  
  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);
  
  const handleSendMessage = (content) => {
    if (settings?.stream) {
      // Use streaming response
      streamResponse?.(content);
    } else {
      // Use non-streaming (send and wait for response)
      sendUserMessage?.(content);
    }
  };
  
  // Handle navigation to a specific message in history
  const handleNavigate = (messageId) => {
    if (messageId) {
      navigateHistory?.(messageId);
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
              messages.map(message => (
                <Message 
                  key={message.id || `streaming-${Date.now()}`} 
                  message={message}
                  onNavigate={handleNavigate}
                />
              ))
            )}
            <div ref={messagesEndRef} />
          </div>
          
          <MessageInput 
            onSend={handleSendMessage} 
            disabled={isStreaming}
            placeholder={isStreaming ? "Waiting for response..." : "Type a message..."}
          />
        </>
      )}
    </div>
  );
};

export default ChatInterface;
