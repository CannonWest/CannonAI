// Modern JavaScript for Gemini Chat UI
document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const messagesContainer = document.getElementById('messages-container');
    const conversationsList = document.getElementById('conversations-list');
    const newChatButton = document.getElementById('new-chat-btn');
    const settingsToggle = document.getElementById('settings-toggle');
    const closeSettings = document.getElementById('close-settings');
    const settingsSidebar = document.querySelector('.settings-sidebar');
    const currentChatTitle = document.getElementById('current-chat-title');
    const modelIndicator = document.getElementById('model-indicator');
    
    // Parameter elements
    const modelSelector = document.getElementById('model-selector');
    const temperatureSlider = document.getElementById('temperature');
    const temperatureValue = document.getElementById('temperature-value');
    const maxTokensSlider = document.getElementById('max-tokens');
    const maxTokensValue = document.getElementById('max-tokens-value');
    const topPSlider = document.getElementById('top-p');
    const topPValue = document.getElementById('top-p-value');
    const topKSlider = document.getElementById('top-k');
    const topKValue = document.getElementById('top-k-value');
    const streamingToggle = document.getElementById('streaming-toggle');
    const saveSettingsButton = document.getElementById('save-settings');
    
    // WebSocket Connection
    let ws;
    let isConnected = false;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    
    // Chat State
    let currentModel = 'gemini-2.0-flash';
    let streamingMode = true;
    let currentConversationTitle = 'New Conversation';
    let parameters = {
        temperature: 0.7,
        max_output_tokens: 1024,
        top_p: 0.9,
        top_k: 40
    };
    
    // Function to update the model selector with fetched models
    function updateModelSelector(models) {
        if (!models || !Array.isArray(models) || models.length === 0) {
            console.log('No models available to populate selector');
            return;
        }
        
        console.log(`Received ${models.length} models to update selector:`);
        models.forEach(model => {
            console.log(`- ${model.name}: ${model.display_name || 'No display name'}`);
        });
        
        // Clear existing options
        modelSelector.innerHTML = '';
        
        // Add each model as an option
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name;
            option.textContent = model.display_name || model.name;
            
            // Set the current model as selected
            if (model.name === currentModel) {
                option.selected = true;
            }
            
            modelSelector.appendChild(option);
        });
        
        console.log(`Updated model selector with ${models.length} models`);
    }
    
    // Function to fetch available models from the server
    function fetchAvailableModels() {
        // Check if WebSocket is initialized and connected
        if (ws && ws.readyState === WebSocket.OPEN) {
            console.log('Fetching available models from server...');
            displaySystemMessage('Fetching available models...');
            sendCommand('/fetch_models');
        } else {
            console.log('Not connected to server. Cannot fetch models.');
            displaySystemMessage('Not connected to server. Cannot fetch models.');
        }
    }
    
    // Initialize WebSocket Connection
    function initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        console.log(`Connecting to WebSocket at ${wsUrl}`);
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            console.log('WebSocket connection established');
            isConnected = true;
            reconnectAttempts = 0;
            displaySystemMessage('Connected to server');
            
            // Request initial state
            sendCommand('/ui_refresh');
        };
        
        ws.onclose = function(event) {
            console.log('WebSocket connection closed', event);
            isConnected = false;
            
            // Attempt to reconnect with exponential backoff
            if (reconnectAttempts < maxReconnectAttempts) {
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                reconnectAttempts++;
                
                displaySystemMessage(`Connection lost. Reconnecting in ${delay/1000} seconds...`);
                
                setTimeout(function() {
                    initWebSocket();
                }, delay);
            } else {
                displaySystemMessage('Could not reconnect to server. Please refresh the page.');
            }
        };
        
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            displaySystemMessage('Error connecting to server');
        };
        
        ws.onmessage = handleWebSocketMessage;
    }
    
    // Process Messages from the Server
    function handleWebSocketMessage(event) {
        const data = JSON.parse(event.data);
        console.log('Received message:', data);
        
        switch (data.type) {
            case 'state_update':
                updateUIState(data);
                break;
            
            case 'history':
                updateConversationHistory(data.content);
                break;
            
            case 'user_message':
                addUserMessageToUI(data.content);
                break;
            
            case 'assistant_message':
                addAIMessageToUI(data.content);
                hideTypingIndicator();
                break;
            
            case 'assistant_start':
                showTypingIndicator();
                startNewAIMessage();
                break;
            
            case 'assistant_chunk':
                appendToCurrentAIMessage(data.content);
                break;
            
            case 'assistant_end':
                finalizeCurrentAIMessage();
                hideTypingIndicator();
                break;
            
            case 'system':
                displaySystemMessage(data.content);
                break;
            
            case 'help':
                displayHelpMessage(data.content);
                break;
            
            case 'conversation_list':
                updateConversationsList(data.content, data.conversations);
                break;
                
            case 'available_models':
                updateModelSelector(data.models);
                break;
            
            default:
                console.warn('Unknown message type:', data.type);
        }
    }
    
    // Send a message to the server
    function sendMessage(message) {
        if (!isConnected) {
            displaySystemMessage('Not connected to server');
            return;
        }
        
        ws.send(message);
        userInput.value = '';
        adjustTextareaHeight();
    }
    
    // Send a command to the server
    function sendCommand(command) {
        if (!isConnected) {
            displaySystemMessage('Not connected to server');
            return;
        }
        
        ws.send(command);
    }
    
    // UI Update Functions
    function updateUIState(state) {
        // Update model info
        currentModel = state.model;
        modelIndicator.textContent = state.model;
        
        // Try to set the model in the selector
        try {
            modelSelector.value = state.model;
            
            // Update max tokens range based on model
            updateMaxTokensRangeForModel(state.model);
        } catch (e) {
            console.log(`Model ${state.model} not found in selector, will be updated when models are fetched`);
        }
        
        // Update streaming mode
        streamingMode = state.streaming;
        streamingToggle.checked = state.streaming;
        
        // Update conversation title
        currentConversationTitle = state.conversation_name;
        currentChatTitle.textContent = state.conversation_name;
        
        // Update parameters
        if (state.params) {
            parameters = state.params;
            updateParameterSliders();
        }
    }
    
    function updateParameterSliders() {
        // Update temperature
        temperatureSlider.value = parameters.temperature;
        temperatureValue.textContent = parameters.temperature;
        
        // Update max tokens
        maxTokensSlider.value = parameters.max_output_tokens;
        maxTokensValue.textContent = parameters.max_output_tokens;
        
        // Update top_p
        topPSlider.value = parameters.top_p;
        topPValue.textContent = parameters.top_p;
        
        // Update top_k
        topKSlider.value = parameters.top_k;
        topKValue.textContent = parameters.top_k;
    }
    
    function updateConversationHistory(messages) {
        // Clear the messages container
        messagesContainer.innerHTML = '';
        
        // If no messages, show a welcome message
        if (!messages || messages.length === 0) {
            displaySystemMessage('Start a new conversation or load a saved one.');
            return;
        }
        
        // Add each message to the UI
        messages.forEach(message => {
            if (message.role === 'user') {
                addUserMessageToUI(message.content);
            } else if (message.role === 'ai' || message.role === 'assistant') {
                addAIMessageToUI(message.content);
            }
        });
        
        // Scroll to the bottom
        scrollToBottom();
    }
    
    function addUserMessageToUI(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message user-message';
        messageElement.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-content">
                <p>${escapeHtml(message)}</p>
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }
    
    let currentAIMessageElement = null;
    
    function addAIMessageToUI(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message ai-message';
        
        // Format with markdown
        const formattedContent = marked.parse(message);
        
        messageElement.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content markdown-content">
                ${formattedContent}
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        
        // Apply syntax highlighting to code blocks
        messageElement.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
        
        scrollToBottom();
    }
    
    function startNewAIMessage() {
        currentAIMessageElement = document.createElement('div');
        currentAIMessageElement.className = 'message ai-message';
        currentAIMessageElement.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content markdown-content">
                <p></p>
            </div>
        `;
        
        messagesContainer.appendChild(currentAIMessageElement);
        scrollToBottom();
    }
    
    function appendToCurrentAIMessage(chunk) {
        if (!currentAIMessageElement) {
            startNewAIMessage();
        }
        
        const contentContainer = currentAIMessageElement.querySelector('.message-content');
        const lastParagraph = contentContainer.querySelector('p:last-child') || document.createElement('p');
        
        // If this is a new paragraph
        if (chunk.startsWith('\n\n')) {
            const newText = chunk.replace(/^\n\n/, '');
            const newParagraph = document.createElement('p');
            newParagraph.textContent = newText;
            contentContainer.appendChild(newParagraph);
        } else {
            // Otherwise append to the current paragraph
            if (!contentContainer.contains(lastParagraph)) {
                contentContainer.appendChild(lastParagraph);
            }
            lastParagraph.textContent += chunk;
        }
        
        scrollToBottom();
    }
    
    function finalizeCurrentAIMessage() {
        if (currentAIMessageElement) {
            const contentContainer = currentAIMessageElement.querySelector('.message-content');
            const rawContent = contentContainer.textContent;
            
            // Replace content with markdown formatted version
            contentContainer.innerHTML = marked.parse(rawContent);
            
            // Apply syntax highlighting
            currentAIMessageElement.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
            
            currentAIMessageElement = null;
        }
    }
    
    function displaySystemMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message system-message';
        messageElement.innerHTML = `
            <div class="message-content">
                <p>${escapeHtml(message)}</p>
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }
    
    function displayHelpMessage(message) {
        const messageElement = document.createElement('div');
        messageElement.className = 'message system-message';
        messageElement.innerHTML = `
            <div class="message-content markdown-content">
                ${marked.parse(message)}
            </div>
        `;
        
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }
    
    function updateConversationsList(formattedList, conversations) {
        // Clear the current list
        conversationsList.innerHTML = '';
        
        // Display the conversations
        if (conversations && conversations.length > 0) {
            conversations.forEach((title, index) => {
                const itemElement = document.createElement('div');
                itemElement.className = 'conversation-item';
                if (title === currentConversationTitle) {
                    itemElement.classList.add('active');
                }
                
                itemElement.innerHTML = `
                    <div class="conversation-title">${escapeHtml(title)}</div>
                    <div class="conversation-actions">
                        <button class="icon-button rename-conversation" data-title="${escapeHtml(title)}">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button class="icon-button delete-conversation" data-title="${escapeHtml(title)}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `;
                
                // Add click event to load the conversation
                itemElement.querySelector('.conversation-title').addEventListener('click', function() {
                    loadConversation(title);
                });
                
                // Add rename and delete event listeners
                itemElement.querySelector('.rename-conversation').addEventListener('click', function(e) {
                    e.stopPropagation();
                    renameConversation(title);
                });
                
                itemElement.querySelector('.delete-conversation').addEventListener('click', function(e) {
                    e.stopPropagation();
                    deleteConversation(title);
                });
                
                conversationsList.appendChild(itemElement);
            });
        } else {
            // No conversations
            const noConversationsElement = document.createElement('div');
            noConversationsElement.className = 'no-conversations';
            noConversationsElement.textContent = 'No saved conversations';
            conversationsList.appendChild(noConversationsElement);
        }
        
        // Show the formatted list as a system message
        displaySystemMessage(formattedList);
    }
    
    // Helper Functions
    function showTypingIndicator() {
        const typingIndicator = document.querySelector('.typing-indicator');
        typingIndicator.classList.remove('hidden');
    }
    
    function hideTypingIndicator() {
        const typingIndicator = document.querySelector('.typing-indicator');
        typingIndicator.classList.add('hidden');
    }
    
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
    
    function adjustTextareaHeight() {
        userInput.style.height = 'auto';
        userInput.style.height = (userInput.scrollHeight) + 'px';
    }
    
    // UI Action Functions
    function sendUserMessage() {
        const message = userInput.value.trim();
        if (!message) return;
        
        // Don't add the message to UI here - wait for server confirmation
        sendMessage(message);
    }
    
    function createNewConversation() {
        // Prompt for conversation name
        const title = prompt('Enter a name for the new conversation:', 'New Conversation');
        if (title) {
            sendCommand(`/new ${title}`);
        }
    }
    
    function loadConversation(title) {
        sendCommand(`/load ${title}`);
    }
    
    function renameConversation(title) {
        const newTitle = prompt('Enter a new name for the conversation:', title);
        if (newTitle && newTitle !== title) {
            sendCommand(`/rename ${title} ${newTitle}`);
        }
    }
    
    function deleteConversation(title) {
        if (confirm(`Are you sure you want to delete "${title}"?`)) {
            sendCommand(`/delete ${title}`);
        }
    }
    
    function toggleSettingsSidebar() {
        const isCollapsed = settingsSidebar.classList.contains('collapsed');
        settingsSidebar.classList.toggle('collapsed');
        
        // If we're opening the sidebar, fetch the latest models
        if (isCollapsed) {
            console.log('Settings sidebar opened, fetching available models...');
            fetchAvailableModels();
        }
    }
    
    function saveSettings() {
        // Collect settings values
        const newSettings = {
            model: modelSelector.value,
            temperature: parseFloat(temperatureSlider.value),
            max_output_tokens: parseInt(maxTokensSlider.value),
            top_p: parseFloat(topPSlider.value),
            top_k: parseInt(topKSlider.value),
            streaming: streamingToggle.checked
        };
        
        // Update model
        if (newSettings.model !== currentModel) {
            sendCommand(`/model ${newSettings.model}`);
        }
        
        // Update streaming mode
        if (newSettings.streaming !== streamingMode) {
            sendCommand('/stream');
        }
        
        // Update parameters
        let paramCommand = '/params';
        if (newSettings.temperature !== parameters.temperature) {
            paramCommand += ` temperature=${newSettings.temperature}`;
        }
        if (newSettings.max_output_tokens !== parameters.max_output_tokens) {
            paramCommand += ` max_output_tokens=${newSettings.max_output_tokens}`;
        }
        if (newSettings.top_p !== parameters.top_p) {
            paramCommand += ` top_p=${newSettings.top_p}`;
        }
        if (newSettings.top_k !== parameters.top_k) {
            paramCommand += ` top_k=${newSettings.top_k}`;
        }
        
        if (paramCommand !== '/params') {
            sendCommand(paramCommand);
        }
        
        // Close settings panel
        toggleSettingsSidebar();
        
        // Display confirmation
        displaySystemMessage('Settings updated');
    }
    
    // Event Listeners
    sendButton.addEventListener('click', sendUserMessage);
    
    userInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendUserMessage();
        }
    });
    
    userInput.addEventListener('input', adjustTextareaHeight);
    
    newChatButton.addEventListener('click', createNewConversation);
    
    settingsToggle.addEventListener('click', toggleSettingsSidebar);
    closeSettings.addEventListener('click', toggleSettingsSidebar);
    
    // Parameter value updates
    temperatureSlider.addEventListener('input', function() {
        temperatureValue.textContent = this.value;
    });
    
    maxTokensSlider.addEventListener('input', function() {
        maxTokensValue.textContent = this.value;
    });
    
    topPSlider.addEventListener('input', function() {
        topPValue.textContent = this.value;
    });
    
    topKSlider.addEventListener('input', function() {
        topKValue.textContent = this.value;
    });
    
    saveSettingsButton.addEventListener('click', saveSettings);
    
    // Add event listener for model selection change
    modelSelector.addEventListener('change', function() {
        console.log(`Model changed to: ${this.value}`);
        updateMaxTokensRangeForModel(this.value);
    });
    
    // Add event listener for streaming toggle
    streamingToggle.addEventListener('change', function() {
        console.log(`Streaming mode toggled to: ${this.checked}`);
        // Send the streaming toggle command immediately
        sendCommand('/stream');
    });
    
        // Function to update max tokens range based on selected model
    function updateMaxTokensRangeForModel(modelName) {
        console.log(`Updating max tokens range for model: ${modelName}`);
        
        // Default values
        let minTokens = 256;
        let maxTokens = 8192;
        let defaultValue = 1024;
        
        // Adjust based on model (update these values based on actual model capabilities)
        if (modelName.includes('flash')) {
            maxTokens = 4096;
            defaultValue = Math.min(parameters.max_output_tokens || 1024, maxTokens);
        } else if (modelName.includes('pro')) {
            maxTokens = 8192;
            defaultValue = Math.min(parameters.max_output_tokens || 2048, maxTokens);
        } else if (modelName.includes('vision')) {
            maxTokens = 4096;
            defaultValue = Math.min(parameters.max_output_tokens || 1024, maxTokens);
        }
        
        // Update the slider attributes
        maxTokensSlider.min = minTokens;
        maxTokensSlider.max = maxTokens;
        maxTokensSlider.value = defaultValue;
        maxTokensValue.textContent = defaultValue;
        
        console.log(`Updated max tokens range: min=${minTokens}, max=${maxTokens}, current=${defaultValue}`);
    }
    
    // Initialize the chat
    initWebSocket();
    
    // Add keyboard shortcut for settings (Ctrl+,)
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === ',') {
            toggleSettingsSidebar();
        }
    });
});
