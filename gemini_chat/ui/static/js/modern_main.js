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
    let currentModel = 'gemini-2.0-flash'; // Default, will be updated by server
    let streamingMode = true;
    let currentConversationTitle = 'New Conversation';
    let parameters = {
        temperature: 0.7,
        max_output_tokens: 1024, // Default, will be updated
        top_p: 0.9,
        top_k: 40
    };
    // Global store for models fetched from the server
    if (typeof window.availableModels === 'undefined') {
        window.availableModels = [];
    }

    // Function to update the model selector with fetched models
    function updateModelSelector(models) {
        if (!models || !Array.isArray(models)) {
            console.warn('Invalid models data received for selector:', models);
            window.availableModels = [];
            modelSelector.innerHTML = '<option value="">Error loading models</option>';
            return;
        }
        if (models.length === 0) {
            console.log('No models available to populate selector');
            window.availableModels = [];
            modelSelector.innerHTML = '<option value="">No models available</option>';
            // Potentially update slider to a generic fallback if no models means no info
            updateMaxTokensRangeForModel(""); // Pass empty to signify no specific model
            return;
        }

        console.log(`Populating model selector with ${models.length} models. Current client-side model: ${currentModel}`);
        window.availableModels = models; // Store/update the global list

        const previouslySelectedValue = modelSelector.value;
        modelSelector.innerHTML = ''; // Clear existing options

        let currentModelOptionExists = false;
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.name; // Full path like "models/gemini-2.0-flash"
            option.textContent = model.display_name || model.name;
            modelSelector.appendChild(option);
            if (model.name === currentModel) {
                option.selected = true;
                currentModelOptionExists = true;
            }
        });

        if (currentModelOptionExists) {
            console.log(`In updateModelSelector, currentModel (${currentModel}) was found and selected.`);
            modelSelector.value = currentModel; // Explicitly set value
        } else if (previouslySelectedValue && models.some(m => m.name === previouslySelectedValue)) {
            // If currentModel wasn't in the new list, but the previously selected one is, keep it.
            modelSelector.value = previouslySelectedValue;
            currentModel = previouslySelectedValue; // Update currentModel to reflect this
            console.log(`In updateModelSelector, currentModel (${currentModel}) not in new list, restored previous selection: ${previouslySelectedValue}`);
        } else if (models.length > 0) {
            // Fallback: select the first model in the new list
            modelSelector.value = models[0].name;
            currentModel = models[0].name; // Update currentModel
            console.log(`In updateModelSelector, neither currentModel nor previous selection found/valid. Selected first model: ${currentModel}`);
        } else {
            // No models, should have been caught earlier
            modelSelector.innerHTML = '<option value="">No models</option>';
            currentModel = "";
        }

        console.log(`Updated model selector. Final selected value: ${modelSelector.value}`);
        // After updating the selector and potentially changing currentModel, refresh the token range
        if (modelSelector.value) {
            updateMaxTokensRangeForModel(modelSelector.value);
        }
    }

    // Function to fetch available models from the server
    function fetchAvailableModels() {
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
            sendCommand('/ui_refresh'); // Request initial state
        };

        ws.onclose = function(event) {
            console.log('WebSocket connection closed', event);
            isConnected = false;
            if (reconnectAttempts < maxReconnectAttempts) {
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                reconnectAttempts++;
                displaySystemMessage(`Connection lost. Reconnecting in ${delay/1000} seconds...`);
                setTimeout(initWebSocket, delay);
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
                updateModelSelector(data.models); // This populates window.availableModels
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
        console.log(`Sending command: ${command}`);
        ws.send(command);
    }

    // UI Update Functions
    function updateUIState(state) {
        console.log("Received state_update:", JSON.parse(JSON.stringify(state)));
        currentModel = state.model; // Update global currentModel
        modelIndicator.textContent = state.model.includes('/') ? state.model.split('/')[1] : state.model;

        // Attempt to set the dropdown selection.
        const modelOption = Array.from(modelSelector.options).find(opt => opt.value === state.model);
        if (modelOption) {
            modelSelector.value = state.model;
            console.log(`In updateUIState, successfully set modelSelector.value to: ${state.model}`);
        } else {
            console.warn(`In updateUIState, model ${state.model} not found in dropdown. updateModelSelector should handle if models list arrives/changes.`);
        }

        // Update max tokens range based on the new state.model.
        // This relies on window.availableModels being populated or its own fallback logic.
        updateMaxTokensRangeForModel(state.model);

        streamingMode = state.streaming;
        streamingToggle.checked = state.streaming;

        currentConversationTitle = state.conversation_name;
        currentChatTitle.textContent = state.conversation_name;

        if (state.params) {
            // Merge new params with existing ones, prioritizing server state
            parameters = { ...parameters, ...state.params };

            // Sync parameters.max_output_tokens with what the slider now shows (after model constraints)
            // This ensures the parameters object reflects the actual cap.
            parameters.max_output_tokens = parseInt(maxTokensSlider.value, 10);
            console.log(`In updateUIState, after model update, parameters.max_output_tokens synced to slider value: ${parameters.max_output_tokens}`);

            updateParameterSliders(); // Visually update all sliders based on the 'parameters' object
        }
    }

    function updateMaxTokensRangeForModel(modelName) {
        console.log(`Attempting to update max tokens range for model: ${modelName}`);
        // For debugging: console.log('Current window.availableModels:', JSON.parse(JSON.stringify(window.availableModels)));

        let minTokens = 256;
        let modelMaxCapability = 8192; // Default model capability if not found or specified
        // let newSliderValue = parameters.max_output_tokens || 1024; // OLD: Start with current user setting

        if (modelName && window.availableModels && window.availableModels.length > 0) {
            const modelData = window.availableModels.find(m => m.name === modelName || m.name.endsWith(modelName));

            if (modelData) {
                // console.log(`Found modelData for ${modelName}:`, JSON.parse(JSON.stringify(modelData)));
                const modelOutputLimit = parseInt(modelData.output_token_limit, 10);
                if (!isNaN(modelOutputLimit) && modelOutputLimit > 0) {
                    modelMaxCapability = modelOutputLimit;
                    console.log(`Model ${modelName} specific output_token_limit: ${modelMaxCapability}`);
                } else {
                    console.log(`Using fallback max capability for ${modelName} (output_token_limit: ${modelData.output_token_limit}). Applying keyword-based fallback.`);
                    if (modelName.includes('flash')) modelMaxCapability = 4096;
                    else if (modelName.includes('pro')) modelMaxCapability = 8192; // Including 'gemini-2.5-pro-preview'
                    else if (modelName.includes('vision')) modelMaxCapability = 4096;
                    // else modelMaxCapability remains default 8192
                }
            } else {
                console.log(`Model ${modelName} not found in window.availableModels. Using generic fallback max capability.`);
                modelMaxCapability = 2048; // More generic fallback
            }
        } else if (!modelName) {
             console.log("No modelName provided to updateMaxTokensRangeForModel, using default capability.");
             modelMaxCapability = 8192; // Default if no model selected
        } else {
            console.log("window.availableModels not ready or empty. Using default capability for slider.");
            modelMaxCapability = 8192;
        }

        // MODIFIED: Default newSliderValue to the model's max capability
        let newSliderValue = modelMaxCapability;

        // Clamp the user's desired value (newSliderValue) by the model's capability
        newSliderValue = Math.min(newSliderValue, modelMaxCapability);
        newSliderValue = Math.max(newSliderValue, minTokens);

        maxTokensSlider.min = minTokens;
        maxTokensSlider.max = modelMaxCapability;   // Set the slider's actual max capability
        maxTokensSlider.value = newSliderValue;     // Set the slider's current position
        maxTokensValue.textContent = newSliderValue; // Update the displayed number

        // Update the global parameters object to reflect this new effective value
        parameters.max_output_tokens = newSliderValue;

        console.log(`Updated max tokens slider: min=${maxTokensSlider.min}, max=${maxTokensSlider.max}, value=${maxTokensSlider.value}. parameters.max_output_tokens is now ${parameters.max_output_tokens}.`);
    }


    function updateParameterSliders() {
        console.log("Updating parameter sliders with values from 'parameters' object:", JSON.parse(JSON.stringify(parameters)));
        temperatureSlider.value = parameters.temperature;
        temperatureValue.textContent = parameters.temperature;

        // For Max Tokens, ensure the slider's value reflects `parameters.max_output_tokens`
        // but clamped within the slider's current actual min/max (set by updateMaxTokensRangeForModel)
        const currentSliderMin = parseInt(maxTokensSlider.min, 10);
        const currentSliderMax = parseInt(maxTokensSlider.max, 10);
        let effectiveMaxTokens = parameters.max_output_tokens;

        if (parameters.max_output_tokens > currentSliderMax) {
            effectiveMaxTokens = currentSliderMax;
        }
        if (parameters.max_output_tokens < currentSliderMin) {
            effectiveMaxTokens = currentSliderMin;
        }

        maxTokensSlider.value = effectiveMaxTokens;
        maxTokensValue.textContent = effectiveMaxTokens;
        // If clamping occurred, we might want to update parameters.max_output_tokens,
        // but updateMaxTokensRangeForModel and updateUIState should have handled this sync.
        // This function primarily makes the UI reflect the 'parameters' state.

        topPSlider.value = parameters.top_p;
        topPValue.textContent = parameters.top_p;

        topKSlider.value = parameters.top_k;
        topKValue.textContent = parameters.top_k;
        console.log("Parameter sliders visually updated.");
    }


    function updateConversationHistory(messages) {
        messagesContainer.innerHTML = '';
        if (!messages || messages.length === 0) {
            displaySystemMessage('Start a new conversation or load a saved one.');
            return;
        }
        messages.forEach(message => {
            if (message.role === 'user') {
                addUserMessageToUI(message.content);
            } else if (message.role === 'ai' || message.role === 'assistant') {
                addAIMessageToUI(message.content);
            }
        });
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
                <p></p> </div>
        `;
        messagesContainer.appendChild(currentAIMessageElement);
        scrollToBottom();
    }

    function appendToCurrentAIMessage(chunk) {
        if (!currentAIMessageElement) {
            startNewAIMessage(); // Should ideally not happen if assistant_start was received
        }
        const contentContainer = currentAIMessageElement.querySelector('.message-content');
        // Directly append to the innerHTML for now, will be parsed fully at the end.
        // This is a simplified approach for streaming; a more robust one would build a text buffer.
        contentContainer.innerHTML = marked.parse(contentContainer.textContent + chunk); // Re-parse on each chunk
        scrollToBottom();
    }

    function finalizeCurrentAIMessage() {
        if (currentAIMessageElement) {
            const contentContainer = currentAIMessageElement.querySelector('.message-content');
            // The content should have been incrementally built by appendToCurrentAIMessage
            // Now, just ensure syntax highlighting is applied if not already.
            contentContainer.querySelectorAll('pre code').forEach((block) => {
                if (!block.dataset.highlighted) { // Avoid re-highlighting
                    hljs.highlightElement(block);
                }
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
        messageElement.className = 'message system-message'; // Or a dedicated help style
        messageElement.innerHTML = `
            <div class="message-content markdown-content">
                ${marked.parse(message)}
            </div>
        `;
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }

    function updateConversationsList(formattedList, conversations) {
        conversationsList.innerHTML = '';
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
                itemElement.querySelector('.conversation-title').addEventListener('click', function() {
                    loadConversation(title);
                });
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
            const noConversationsElement = document.createElement('div');
            noConversationsElement.className = 'no-conversations';
            noConversationsElement.textContent = 'No saved conversations';
            conversationsList.appendChild(noConversationsElement);
        }
        // displaySystemMessage(formattedList); // Optionally show the raw list
    }

    // Helper Functions
    function showTypingIndicator() {
        document.querySelector('.typing-indicator').classList.remove('hidden');
    }

    function hideTypingIndicator() {
        document.querySelector('.typing-indicator').classList.add('hidden');
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
        sendMessage(message); // Server will echo back as 'user_message'
    }

    function createNewConversation() {
        const title = prompt('Enter a name for the new conversation:', `Chat ${new Date().toLocaleTimeString()}`);
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
        if (isCollapsed) { // Means it's now opening
            fetchAvailableModels();
        }
    }

    function saveSettings() {
        const newModel = modelSelector.value;
        // Send /model command if changed
        if (newModel !== currentModel) {
            sendCommand(`/model ${newModel}`);
            // currentModel will be updated via state_update from server
        }

        // Collect parameters from sliders
        const newParams = {
            temperature: parseFloat(temperatureSlider.value),
            max_output_tokens: parseInt(maxTokensSlider.value), // Read directly from slider
            top_p: parseFloat(topPSlider.value),
            top_k: parseInt(topKSlider.value)
        };

        let paramCommandParts = [];
        for (const key in newParams) {
            if (newParams[key] !== parameters[key]) {
                paramCommandParts.push(`${key}=${newParams[key]}`);
            }
        }

        if (paramCommandParts.length > 0) {
            sendCommand(`/params ${paramCommandParts.join(' ')}`);
        }

        // Streaming mode is handled on toggle, but ensure consistency if needed
        const newStreamingMode = streamingToggle.checked;
        if (newStreamingMode !== streamingMode) {
            sendCommand('/stream'); // Server will confirm with state_update
        }

        // Optimistically update client-side parameters, server will send state_update to confirm
        parameters = { ...parameters, ...newParams };
        streamingMode = newStreamingMode;


        // No need to manually close sidebar if it's part of the flow,
        // but if it's a separate action:
        // settingsSidebar.classList.add('collapsed');
        displaySystemMessage('Settings sent to server. Awaiting confirmation.');
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

    // Parameter value updates (for display only)
    temperatureSlider.addEventListener('input', function() { temperatureValue.textContent = this.value; });
    maxTokensSlider.addEventListener('input', function() { maxTokensValue.textContent = this.value; });
    topPSlider.addEventListener('input', function() { topPValue.textContent = this.value; });
    topKSlider.addEventListener('input', function() { topKValue.textContent = this.value; });

    saveSettingsButton.addEventListener('click', saveSettings);

    modelSelector.addEventListener('change', function() {
        console.log(`Model dropdown changed to: ${this.value}`);
        // When user manually changes the model, update the token range immediately
        // This will also set the slider value to the model's max capability.
        updateMaxTokensRangeForModel(this.value);
        // Note: The actual model change command (/model) is sent when "Save Settings" is clicked.
    });

    streamingToggle.addEventListener('change', function() {
        console.log(`Streaming mode toggled to: ${this.checked}`);
        // Send command immediately as per existing logic
        sendCommand('/stream');
    });

    // Initialize the chat
    initWebSocket();
    adjustTextareaHeight(); // Initial adjustment

    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === ',') {
            e.preventDefault();
            toggleSettingsSidebar();
        }
    });
});
1