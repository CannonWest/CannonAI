import { useState, useEffect, useCallback, useRef } from 'react';
import WebSocketService from '../services/websocket';

export const useWebSocket = (url) => {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [error, setError] = useState(null);
  
  // Use refs to store callbacks that we'll attach to the WebSocket service
  const callbackRefs = useRef({
    message: null,
    open: null,
    close: null,
    error: null
  });
  
  // Connect to WebSocket on mount or when URL changes
  useEffect(() => {
    if (!url) return;
    
    // Define the callbacks
    const onOpen = () => {
      setIsConnected(true);
      setError(null);
    };
    
    const onClose = () => {
      setIsConnected(false);
    };
    
    const onMessage = (data) => {
      setLastMessage(data);
    };
    
    const onError = (err) => {
      setError(err);
    };
    
    // Store callbacks in refs so we can remove them later
    callbackRefs.current = {
      message: onMessage,
      open: onOpen,
      close: onClose,
      error: onError
    };
    
    // Register callbacks with WebSocket service
    WebSocketService.onOpen(onOpen);
    WebSocketService.onClose(onClose);
    WebSocketService.onMessage(onMessage);
    WebSocketService.onError(onError);
    
    // Connect to the WebSocket
    WebSocketService.connect(url);
    
    // Cleanup function to disconnect and remove callbacks
    return () => {
      WebSocketService.removeCallback('open', callbackRefs.current.open);
      WebSocketService.removeCallback('close', callbackRefs.current.close);
      WebSocketService.removeCallback('message', callbackRefs.current.message);
      WebSocketService.removeCallback('error', callbackRefs.current.error);
      
      WebSocketService.disconnect();
    };
  }, [url]);
  
  // Define the sendMessage function
  const sendMessage = useCallback((data) => {
    if (!isConnected) {
      console.warn('Cannot send message: WebSocket is not connected');
      return false;
    }
    
    return WebSocketService.send(data);
  }, [isConnected]);
  
  // Method to manually reconnect
  const reconnect = useCallback(() => {
    WebSocketService.disconnect();
    WebSocketService.connect(url);
  }, [url]);

  return {
    isConnected,
    lastMessage,
    error,
    sendMessage,
    reconnect
  };
};
