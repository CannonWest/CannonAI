// Main JavaScript for Gemini Chat Web UI
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const conversation = document.getElementById('conversation');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const modelDisplay = document.getElementById('model-display');
    const streamingDisplay = document.getElementById('streaming-display');
    const connectionStatus = document.getElementById('connection-status');
    const thinkingIndicator = document.getElementById('thinkingIndicator');
    const conversationsList = document.getElementById('conversationsList');
    
    // Streaming state
    let isStreaming = false;
    let currentStreamingMessage = null;
    
    // Connection management
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    
    // Initialize WebSocket
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        console.log('Attempting to connect to WebSocket URL:', wsUrl);
        
        // Update connection status
        connectionStatus.textContent = 'Connection: Connecting...';
        connectionStatus.className = 'connecting';
        
        addSystemMessage(`Connecting to server at ${wsUrl}...`);
        ws = new WebSocket(wsUrl);
        
        // Log the WebSocket state changes
        logWebSocketStateChange(ws);
        
        ws.onopen = function() {
            console.log('WebSocket connected successfully');
            addSystemMessage('Connected to Gemini Chat');
            connectionStatus.textContent = 'Connection: Connected';
            connectionStatus.className = 'connected';
            reconnectAttempts = 0;
            
            // Request UI refresh to get initial state
            setTimeout(() => {
                sendMessage('/ui_refresh');
            }, 500);
        };
        
        ws.onmessage = function(event) {
            handleWebSocketMessage(event);
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            // More detailed error information
            console.log('WebSocket readyState at error:', ws.readyState);
            
            // Log the current state of the WebSocket
            const stateDescriptions = {
                0: 'CONNECTING', 
                1: 'OPEN', 
                2: 'CLOSING', 
                3: 'CLOSED'
            };
            
            const stateDesc = stateDescriptions[ws.readyState] || 'UNKNOWN';
            addSystemMessage(`Connection error occurred (State: ${stateDesc})`);
            
            // Update connection status
            connectionStatus.textContent = `Connection: Error (${stateDesc})`;
            connectionStatus.className = 'error';
            
            // Add instructions for common issues
            if (ws.readyState === 3) { // CLOSED
                addSystemMessage('Your connection was rejected. This might be due to:');
                addSystemMessage('1. Security issues (e.g., CORS, origin policy)');
                addSystemMessage('2. Server authentication requirements');
                addSystemMessage('3. Server middleware rejecting the connection');
                addSystemMessage('Check the server logs for more details.');
            }
        };
        
        ws.onclose = function() {
            addSystemMessage('Disconnected from server');
            
            // Update connection status
            connectionStatus.textContent = 'Connection: Disconnected';
            connectionStatus.className = 'disconnected';
            
            // Attempt to reconnect
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = Math.min(1000 * reconnectAttempts, 5000);
                
                addSystemMessage(`Reconnecting in ${delay/1000} seconds...`);
                connectionStatus.textContent = `Connection: Reconnecting in ${delay/1000}s`;
                setTimeout(connectWebSocket, delay);
            } else {
                addSystemMessage('Could not reconnect to server. Please refresh the page.');
                connectionStatus.textContent = 'Connection: Failed - Refresh page';
            }
        };
    }
    
    // Handle messages from the server
    function handleWebSocketMessage(event) {
        const data = JSON.parse(event.data);
        
        switch(data.type) {
            case 'state_update':
                updateUIState(data);
                break;
                
            case 'user_message':
                addUserMessage(data.content);
                showThinkingIndicator(true);
                break;
                
            case 'assistant_message':
                showThinkingIndicator(false);
                addAssistantMessage(data.content);
                break;
                
            case 'assistant_start':
                showThinkingIndicator(false);
                startStreamingMessage();
                break;
                
            case 'assistant_chunk':
                appendToStreamingMessage(data.content);
                break;
                
            case 'assistant_end':
                finishStreamingMessage();
                break;
                
            case 'system':
                showThinkingIndicator(false);
                addSystemMessage(data.content);
                break;
                
            case 'help':
                addHelpMessage(data.content);
                break;
                
            case 'history':
                displayHistory(data.content);
                break;
                
            case 'conversation_list':
                updateConversationsList(data);
                break;
        }
    }
    
    // Update UI state
    function updateUIState(data) {
        // Update model display
        modelDisplay.textContent = `Model: ${data.model}`;
        
        // Update streaming display
        streamingDisplay.textContent = `Streaming: ${data.streaming ? 'Yes' : 'No'}`;
        
        // Update conversation name in title
        document.title = `Gemini Chat - ${data.conversation_name || 'New Conversation'}`;
    }
    
    // Send a message to the server
    function sendMessage(message) {
        if (!message.trim()) return;
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(message);
            userInput.value = '';
            
            // Only add user message for non-command messages
            // The server will echo back user messages
            if (!message.startsWith('/')) {
                showThinkingIndicator(true);
            }
        } else {
            addSystemMessage('Not connected to server');
        }
    }
    
    // Update conversations list
    function updateConversationsList(data) {
        addSystemMessage(data.content);
        
        // Clear existing list
        conversationsList.innerHTML = '';
        
        // Add each conversation
        if (data.conversations && data.conversations.length > 0) {
            data.conversations.forEach((title, index) => {
                const item = document.createElement('div');
                item.className = 'conversation-item';
                item.textContent = `${index + 1}. ${title}`;
                item.addEventListener('click', () => {
                    sendMessage(`/load ${title}`);
                    addSystemMessage(`Loading conversation: ${title}`);
                });
                conversationsList.appendChild(item);
            });
        }
    }
    
    // Message handling functions
    function addUserMessage(content) {
        const msgElement = document.createElement('div');
        msgElement.className = 'message user-message';
        msgElement.textContent = content;
        conversation.appendChild(msgElement);
        scrollToBottom();
    }
    
    function addAssistantMessage(content) {
        const msgElement = document.createElement('div');
        msgElement.className = 'message assistant-message';
        
        // Process markdown-like formatting
        msgElement.innerHTML = formatMessageContent(content);
        
        conversation.appendChild(msgElement);
        scrollToBottom();
    }
    
    function addSystemMessage(content) {
        const msgElement = document.createElement('div');
        msgElement.className = 'message system-message';
        msgElement.innerHTML = formatMessageContent(content);
        conversation.appendChild(msgElement);
        scrollToBottom();
    }
    
    function addHelpMessage(content) {
        const msgElement = document.createElement('div');
        msgElement.className = 'message help-message';
        msgElement.innerHTML = formatMessageContent(content);
        conversation.appendChild(msgElement);
        scrollToBottom();
    }
    
    // Streaming message handling
    function startStreamingMessage() {
        currentStreamingMessage = document.createElement('div');
        currentStreamingMessage.className = 'message assistant-message';
        conversation.appendChild(currentStreamingMessage);
        scrollToBottom();
    }
    
    function appendToStreamingMessage(chunk) {
        if (currentStreamingMessage) {
            // Process markdown incrementally
            const currentContent = currentStreamingMessage.innerHTML || '';
            currentStreamingMessage.innerHTML = formatMessageContent(currentContent + chunk);
            scrollToBottom();
        }
    }
    
    function finishStreamingMessage() {
        currentStreamingMessage = null;
    }
    
    // Display conversation history
    function displayHistory(history) {
        // Clear current conversation
        conversation.innerHTML = '';
        
        // Add each message
        history.forEach(msg => {
            if (msg.role === 'user') {
                addUserMessage(msg.content);
            } else if (msg.role === 'assistant') {
                addAssistantMessage(msg.content);
            }
        });
    }
    
    // Format message content with markdown-like syntax
    function formatMessageContent(text) {
        if (!text) return '';
        
        // Process code blocks with language
        text = text.replace(/```([a-z]*)\n([\s\S]*?)```/g, function(match, language, code) {
            return `<pre><code class="language-${language}">${escapeHtml(code)}</code></pre>`;
        });
        
        // Process code blocks without language
        text = text.replace(/```([\s\S]*?)```/g, function(match, code) {
            return `<pre><code>${escapeHtml(code)}</code></pre>`;
        });
        
        // Process inline code
        text = text.replace(/`([^`]+)`/g, function(match, code) {
            return `<code>${escapeHtml(code)}</code>`;
        });
        
        // Process bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        
        // Process italic
        text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        
        // Process headers
        text = text.replace(/## (.*?)$/gm, '<h3>$1</h3>');
        text = text.replace(/# (.*?)$/gm, '<h2>$1</h2>');
        
        // Process lists
        text = text.replace(/^\s*- (.*?)$/gm, '<li>$1</li>');
        text = text.replace(/(<li>.*?<\/li>)(?:\n|$)/g, '<ul>$1</ul>');
        
        // Fix multiple ul tags
        text = text.replace(/<\/ul>\s*<ul>/g, '');
        
        // Process line breaks
        text = text.replace(/\n/g, '<br>');
        
        return text;
    }
    
    // Helper to escape HTML
    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    
    // Show/hide thinking indicator
    function showThinkingIndicator(show) {
        thinkingIndicator.style.display = show ? 'block' : 'none';
    }
    
    // Scroll conversation to bottom
    function scrollToBottom() {
        conversation.scrollTop = conversation.scrollHeight;
    }
    
    // Helper function to log WebSocket state changes
    function logWebSocketStateChange(socket) {
        const states = ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'];
        let lastState = socket.readyState;
        
        console.log(`Initial WebSocket state: ${states[lastState]}`);
        
        // Create a function to check for state changes
        const stateChecker = setInterval(function() {
            if (socket.readyState !== lastState) {
                lastState = socket.readyState;
                console.log(`WebSocket state changed to: ${states[lastState]}`);
                
                // Clear interval if closed state is reached
                if (lastState === 3) {
                    clearInterval(stateChecker);
                }
            }
        }, 100);
        
        // Clear the interval after a reasonable timeout
        setTimeout(() => clearInterval(stateChecker), 10000);
    }
    
    // Connect WebSocket
    connectWebSocket();
    
    // Set up event listeners
    sendButton.addEventListener('click', function() {
        sendMessage(userInput.value);
    });
    
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage(userInput.value);
        }
    });
    
    // Set up command items
    document.querySelectorAll('.command-item').forEach(item => {
        item.addEventListener('click', function() {
            const cmd = this.getAttribute('data-cmd');
            userInput.value = cmd;
            userInput.focus();
        });
    });
    
    // Settings button
    document.getElementById('settingsButton').addEventListener('click', function() {
        sendMessage('/params');
    });
});