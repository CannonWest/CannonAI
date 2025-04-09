// WebSocket service for real-time communication

class WebSocketService {
  constructor() {
    this.socket = null;
    this.callbacks = {
      message: [],
      open: [],
      close: [],
      error: []
    };
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectTimeout = null;
    this.isConnecting = false;
  }

  connect(url) {
    if (this.socket?.readyState === WebSocket.OPEN || this.isConnecting) {
      console.warn('WebSocket is already connected or connecting');
      return;
    }
    
    this.isConnecting = true;
    this.url = url;
    
    console.log(`Connecting to WebSocket: ${url}`);
    this.socket = new WebSocket(url);
    
    this.socket.onopen = (event) => {
      console.log('WebSocket connection established');
      this.isConnecting = false;
      this.reconnectAttempts = 0;
      this._triggerCallbacks('open', event);
    };
    
    this.socket.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        data = event.data;
      }
      this._triggerCallbacks('message', data);
    };
    
    this.socket.onclose = (event) => {
      console.log('WebSocket connection closed', event);
      this.isConnecting = false;
      this._triggerCallbacks('close', event);
      
      // Attempt to reconnect if it wasn't a clean close
      if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
        this._scheduleReconnect();
      }
    };
    
    this.socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.isConnecting = false;
      this._triggerCallbacks('error', error);
    };
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (!this.socket) {
      return;
    }
    
    console.log('Disconnecting WebSocket');
    this.socket.close(1000, 'User initiated disconnect');
    this.socket = null;
  }

  send(data) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error('Cannot send message: WebSocket is not connected');
      return false;
    }
    
    try {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      this.socket.send(message);
      return true;
    } catch (error) {
      console.error('Error sending WebSocket message:', error);
      return false;
    }
  }

  onMessage(callback) {
    if (typeof callback === 'function') {
      this.callbacks.message.push(callback);
    }
  }

  onOpen(callback) {
    if (typeof callback === 'function') {
      this.callbacks.open.push(callback);
    }
  }

  onClose(callback) {
    if (typeof callback === 'function') {
      this.callbacks.close.push(callback);
    }
  }

  onError(callback) {
    if (typeof callback === 'function') {
      this.callbacks.error.push(callback);
    }
  }

  removeCallback(type, callback) {
    if (!this.callbacks[type]) return;
    
    const index = this.callbacks[type].indexOf(callback);
    if (index !== -1) {
      this.callbacks[type].splice(index, 1);
    }
  }

  // Private methods
  _triggerCallbacks(type, data) {
    if (!this.callbacks[type]) return;
    
    for (const callback of this.callbacks[type]) {
      try {
        callback(data);
      } catch (error) {
        console.error(`Error in ${type} callback:`, error);
      }
    }
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 30000);
    
    console.log(`Scheduling WebSocket reconnect attempt ${this.reconnectAttempts} in ${delay}ms`);
    
    this.reconnectTimeout = setTimeout(() => {
      console.log(`Attempting WebSocket reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
      this.connect(this.url);
    }, delay);
  }

  // Check connection status
  isConnected() {
    return this.socket?.readyState === WebSocket.OPEN;
  }
}

export default new WebSocketService();
