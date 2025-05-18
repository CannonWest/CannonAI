import React, { useState, useEffect, useRef } from 'react';
import { Box, Paper, TextField, Button, Typography, CircularProgress, Alert } from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import useWebSocket from 'react-use-websocket';
import { getConversation, getWebSocketUrl, createStreamMessage } from '../services/api';
import MessageBubble from './MessageBubble';

const ChatView = ({ activeConversation, config, clientId, onConversationUpdated }) => {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [streamingMessage, setStreamingMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef(null);
  
  // WebSocket connection for streaming
  const { sendJsonMessage, lastJsonMessage } = useWebSocket(
    getWebSocketUrl(clientId),
    {
      onOpen: () => console.log('WebSocket connected'),
      onClose: () => console.log('WebSocket disconnected'),
      onError: (event) => {
        console.error('WebSocket error:', event);
        setError('WebSocket connection error. Streaming may not work.');
      },
      shouldReconnect: (closeEvent) => true,
      reconnectAttempts: 10,
      reconnectInterval: 3000,
    }
  );
  
  // Load conversation messages when activeConversation changes
  useEffect(() => {
    const loadConversation = async () => {
      if (!activeConversation) return;
      
      try {
        setLoading(true);
        setError(null);
        
        const conversation = await getConversation(activeConversation.conversation_id);
        setMessages(conversation.messages || []);
      } catch (err) {
        console.error('Error loading conversation:', err);
        setError('Failed to load conversation messages');
      } finally {
        setLoading(false);
      }
    };
    
    loadConversation();
  }, [activeConversation]);
  
  // Handle WebSocket messages for streaming
  useEffect(() => {
    if (!lastJsonMessage) return;
    
    const { action, chunk, message: completeMessage, error } = lastJsonMessage;
    
    if (error) {
      setError(`Error: ${error}`);
      setIsStreaming(false);
      return;
    }
    
    switch (action) {
      case 'stream_start':
        setIsStreaming(true);
        setStreamingMessage('');
        break;
        
      case 'stream_chunk':
        setStreamingMessage(prev => prev + chunk);
        break;
        
      case 'stream_end':
        setIsStreaming(false);
        
        // Add the complete AI message to the list
        setMessages(prev => [...prev, completeMessage]);
        setStreamingMessage('');
        break;
        
      case 'message_sent':
        // Add the user message to the list
        setMessages(prev => [...prev, message]);
        break;
        
      default:
        // Handle any other action types
        console.log(`Unhandled WebSocket action: ${action}`);
        break;
    }
  }, [lastJsonMessage, message]);
  
  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);
  
  // Handle sending a message
  const handleSendMessage = async () => {
    if (!message.trim() || !activeConversation) return;
    
    // Check if API key is set
    if (!config.api_key_set) {
      setError('API key not set. Please configure your API key in settings.');
      return;
    }
    
    try {
      setError(null);
      
      // Add user message to the list immediately for better UX
      const userMessage = {
        role: 'user',
        text: message,
      };
      
      setMessages(prev => [...prev, userMessage]);
      
      // Use WebSocket for streaming
      sendJsonMessage(createStreamMessage(message, activeConversation.conversation_id));
      
      // Clear the input
      setMessage('');
    } catch (err) {
      console.error('Error sending message:', err);
      setError('Failed to send message');
    }
  };
  
  // Handle pressing Enter to send
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };
  
  if (!activeConversation) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Typography variant="h6" color="text.secondary">
          No conversation selected. Create a new conversation from the sidebar.
        </Typography>
      </Box>
    );
  }
  
  return (
    <Box sx={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%',
      maxHeight: 'calc(100vh - 80px)', // Account for toolbar and some padding
    }}>
      {/* Messages container */}
      <Box sx={{ 
        flexGrow: 1,
        overflow: 'auto',
        mb: 2,
        p: 2,
        borderRadius: 1,
        bgcolor: 'background.paper'
      }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {messages.map((msg, index) => (
              <MessageBubble 
                key={index}
                message={msg.text}
                isUser={msg.role === 'user'}
              />
            ))}
            
            {/* Streaming message bubble */}
            {isStreaming && streamingMessage && (
              <MessageBubble
                message={streamingMessage}
                isUser={false}
                isStreaming={true}
              />
            )}
            
            {/* Error message */}
            {error && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {error}
              </Alert>
            )}
            
            {/* Invisible element to scroll to */}
            <div ref={messagesEndRef} />
          </>
        )}
      </Box>
      
      {/* Message input */}
      <Paper 
        elevation={3}
        component="form"
        sx={{ 
          p: '2px 4px',
          display: 'flex',
          alignItems: 'center',
        }}
        onSubmit={(e) => {
          e.preventDefault();
          handleSendMessage();
        }}
      >
        <TextField
          fullWidth
          multiline
          maxRows={4}
          placeholder="Type your message here..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isStreaming || loading}
          variant="outlined"
          sx={{ ml: 1, flex: 1 }}
        />
        <Button 
          sx={{ p: '10px' }} 
          color="primary" 
          aria-label="send"
          onClick={handleSendMessage}
          disabled={!message.trim() || isStreaming || loading}
          endIcon={<SendIcon />}
        >
          Send
        </Button>
      </Paper>
    </Box>
  );
};

export default ChatView;
