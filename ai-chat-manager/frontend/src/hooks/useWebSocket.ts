import { useState, useEffect, useCallback, useRef } from 'react';

interface WebSocketMessage {
  type: string;
  content?: string;
  status?: string;
  error?: string;
}

interface UseWebSocketOptions {
  onOpen?: () => void;
  onClose?: () => void;
  onMessage?: (message: WebSocketMessage) => void;
  onError?: (error: Event) => void;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  autoConnect?: boolean;
}

/**
 * Custom hook for WebSocket communication
 */
const useWebSocket = (
  url: string,
  options: UseWebSocketOptions = {}
) => {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Event | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);
  
  // Default options
  const {
    onOpen,
    onClose,
    onMessage,
    onError,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    autoConnect = true
  } = options;
  
  // Store WebSocket instance in a ref
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const urlRef = useRef<string>(url); // Track the current URL
  
  // Create WebSocket connection
  const connect = useCallback(() => {
    // Close existing connection if any
    if (ws.current) {
      ws.current.close();
    }
    
    console.log(`Attempting to connect to WebSocket: ${url}`);
    
    // Create new WebSocket
    try {
      ws.current = new WebSocket(url);
      
      // Setup event handlers
      ws.current.onopen = () => {
        console.log(`WebSocket connection established to ${url}`);
        setIsConnected(true);
        setError(null);
        setReconnectCount(0);
        onOpen && onOpen();
      };
    
    ws.current.onclose = (event) => {
      setIsConnected(false);
      onClose && onClose();
      
      // Attempt to reconnect if not closed cleanly and under max attempts
      if (!event.wasClean && reconnectCount < reconnectAttempts) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(() => {
          setReconnectCount(prev => prev + 1);
          connect();
        }, reconnectInterval);
      }
    };
    
    ws.current.onerror = (event) => {
        console.error(`WebSocket error on ${url}:`, event);
        setError(event);
        onError && onError(event);
      };
    } catch (error) {
      console.error(`Failed to create WebSocket connection to ${url}:`, error);
      setError(error as Event);
      onError && onError(error as Event);
    }
    
    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage;
        onMessage && onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  }, [url, onOpen, onClose, onMessage, onError, reconnectAttempts, reconnectInterval, reconnectCount]);
  
  // Send message to WebSocket
  const sendMessage = useCallback((data: any) => {
    if (ws.current && isConnected) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      ws.current.send(message);
      return true;
    }
    return false;
  }, [isConnected]);
  
  // Manual reconnect
  const reconnect = useCallback(() => {
    if (reconnectCount < reconnectAttempts) {
      setReconnectCount(prev => prev + 1);
      connect();
    }
  }, [connect, reconnectAttempts, reconnectCount]);
  
  // Close WebSocket
  const disconnect = useCallback(() => {
    if (ws.current) {
      ws.current.close();
    }
    clearTimeout(reconnectTimeoutRef.current);
  }, []);
  
  // Initialize WebSocket on mount and cleanup on unmount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);
  
  // Keep WebSocket alive with ping/pong
  useEffect(() => {
    let pingInterval: NodeJS.Timeout;
    
    if (isConnected) {
      pingInterval = setInterval(() => {
        sendMessage({ type: 'ping' });
      }, 30000); // Send ping every 30 seconds
    }
    
    return () => {
      clearInterval(pingInterval);
    };
  }, [isConnected, sendMessage]);
  
  return {
    isConnected,
    error,
    reconnectCount,
    sendMessage,
    reconnect,
    disconnect,
    connect
  };
};

export default useWebSocket;
