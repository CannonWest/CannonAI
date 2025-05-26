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
    
    // Model selection related elements
    let modelDropdown = null; // Will be populated when settings dialog opens
    
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
                
            case 'available_models':
                updateModelDropdown(data.models);
                break;
        }
    }
    
    // Update UI state
    function updateUIState(data) {
        // Update model display
        modelDisplay.textContent = `Model: ${data.model}`;
        
        // Store current model for dropdown selection
        window.currentModel = data.model;
        
        // Update streaming display
        streamingDisplay.textContent = `Streaming: ${data.streaming ? 'Yes' : 'No'}`;
        
        // Update conversation name in title
        document.title = `Gemini Chat - ${data.conversation_name || 'New Conversation'}`;
        
        // If model dropdown exists and currentModel has changed, update selection
        if (modelDropdown && window.currentModel) {
            // Find and select the current model in the dropdown
            const options = modelDropdown.querySelectorAll('option');
            let modelFound = false;
            
            options.forEach(option => {
                // Check for exact match or if the current model ends with the option value
                // (handles both short names and full paths)
                const currentModelShort = window.currentModel.split('/').pop();
                if (option.value === window.currentModel || 
                    option.value === currentModelShort ||
                    window.currentModel.endsWith(option.value)) {
                    option.selected = true;
                    modelFound = true;
                }
            });
            
            // If we couldn't find a match and have models, may need to refresh
            if (!modelFound && options.length > 0) {
                console.log("Current model not found in dropdown. May need to refresh model list.");
            }
        }
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
    // Function to update model dropdown with fetched models
    function updateModelDropdown(models) {
        // If no models were provided, do nothing
        if (!models || !Array.isArray(models) || models.length === 0) {
            addSystemMessage("No models available");
            console.log("No models available to populate dropdown");
            return;
        }
        
        console.log(`Received ${models.length} models to update dropdown:`);
        models.forEach(model => {
            console.log(`- ${model.name}: ${model.display_name || 'No display name'}`);
        });
        
        // If there's no active model dropdown, create the memory but don't update DOM
        if (!modelDropdown) {
            console.log("Model dropdown element not found in DOM yet. Saving models for later use.");
            // Store the models to use when the dialog is created
            window.availableModels = models;
            return;
        }
        
        // Clear existing options
        modelDropdown.innerHTML = '';
        console.log("Cleared existing dropdown options");
        
        // Add each model as an option
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name;
            option.textContent = model.display_name || model.name;
            // If this is the currently selected model, select it
            if (model.name === window.currentModel) {
                option.selected = true;
                console.log(`Selected model: ${model.name}`);
            }
            modelDropdown.appendChild(option);
        });
        
        console.log(`Updated model dropdown with ${models.length} models`);
    }
    
    // Function to fetch available models from the server
    function fetchAvailableModels() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            addSystemMessage("Fetching available models...");
            sendMessage('/fetch_models');
        } else {
            addSystemMessage("Not connected to server. Cannot fetch models.");
        }
    }
    
    // Create model select dropdown with initial models
    function createModelSelection(parentElement) {
        const modelSection = document.createElement('div');
        modelSection.className = 'settings-section';
        
        const modelLabel = document.createElement('h3');
        modelLabel.textContent = 'MODEL';
        modelSection.appendChild(modelLabel);
        
        // Create dropdown for models
        const dropdown = document.createElement('select');
        dropdown.id = 'model-dropdown';
        dropdown.className = 'model-select';
        modelSection.appendChild(dropdown);
        
        // Store reference to the dropdown
        modelDropdown = dropdown;
        
        // Add a button to refresh models
        const refreshButton = document.createElement('button');
        refreshButton.textContent = 'Refresh Models';
        refreshButton.className = 'refresh-models-btn';
        refreshButton.addEventListener('click', fetchAvailableModels);
        modelSection.appendChild(refreshButton);
        
        // Add the section to the parent
        parentElement.appendChild(modelSection);
        
        // Add initial models while we wait for the API response
        const initialModels = [
            { name: 'gemini-2.0-flash', display_name: 'Gemini 2.0 Flash' },
            { name: 'gemini-2.0-pro', display_name: 'Gemini 2.0 Pro' },
            { name: 'gemini-2.0-vision', display_name: 'Gemini 2.0 Vision' }
        ];
        updateModelDropdown(initialModels);
        
        // If we have cached models, use them
        if (window.availableModels) {
            updateModelDropdown(window.availableModels);
        }
        
        // Fetch the latest models from server
        console.log('Fetching available models from server...');
        fetchAvailableModels();
        
        // Handle model selection change
        dropdown.addEventListener('change', function() {
            const selectedModel = this.value;
            console.log(`Model selected: ${selectedModel}`);
            sendMessage(`/model ${selectedModel}`);
        });
    }
    
    // Handle the params command by creating a custom settings dialog
    function createSettingsDialog() {
        // Check if dialog already exists
        let dialog = document.getElementById('settings-dialog');
        if (dialog) {
            // Just show it if it exists
            dialog.style.display = 'block';
            return;
        }
        
        // Create the dialog
        dialog = document.createElement('div');
        dialog.id = 'settings-dialog';
        dialog.className = 'settings-dialog';
        
        // Add header with close button
        const header = document.createElement('div');
        header.className = 'dialog-header';
        
        const title = document.createElement('h2');
        title.textContent = 'Settings';
        header.appendChild(title);
        
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '&times;';
        closeBtn.className = 'close-btn';
        closeBtn.addEventListener('click', function() {
            dialog.style.display = 'none';
        });
        header.appendChild(closeBtn);
        
        dialog.appendChild(header);
        
        // Create content area
        const content = document.createElement('div');
        content.className = 'dialog-content';
        
        // Add model selection section
        createModelSelection(content);
        
        // Add temperature slider (optional)
        // Add other parameter controls here
        
        dialog.appendChild(content);
        
        // Add the dialog to the body
        document.body.appendChild(dialog);
    }
    
    // Replace the old settings button handler
    document.getElementById('settingsButton').addEventListener('click', function() {
        createSettingsDialog();
    });
});