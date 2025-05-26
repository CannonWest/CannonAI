/**
 * Gemini Chat GUI - Frontend JavaScript
 * Handles all UI interactions and communication with the Flask backend
 */

class GeminiChatApp {
    constructor() {
        console.log("[DEBUG] Initializing GeminiChatApp");
        
        this.apiBase = window.location.origin;
        this.currentConversationId = null;
        this.isStreaming = false;
        this.streamingEnabled = false;
        
        // Bootstrap modal instances
        this.modals = {};
        
        // Branch management
        this.messageTree = {}; // Full tree structure
        this.messageElements = {}; // DOM element references
        this.activePath = []; // Current active path of message IDs
        this.activeLeaf = null; // Current leaf message ID
        
        // Initialize on DOM ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }
    
    init() {
        console.log("[DEBUG] DOM ready, initializing app");
        
        // Initialize Bootstrap modals
        this.modals.newConversation = new bootstrap.Modal(document.getElementById('newConversationModal'));
        this.modals.modelSelector = new bootstrap.Modal(document.getElementById('modelSelectorModal'));
        this.modals.settings = new bootstrap.Modal(document.getElementById('settingsModal'));
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Load initial data
        this.loadStatus();
        this.loadConversations();
        
        // Set up periodic status check
        setInterval(() => this.updateConnectionStatus(), 5000);
    }
    
    setupEventListeners() {
        console.log("[DEBUG] Setting up event listeners");
        
        // Message input
        const messageInput = document.getElementById('messageInput');
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Settings form inputs
        const tempSlider = document.getElementById('temperature');
        tempSlider.addEventListener('input', (e) => {
            document.getElementById('temperatureValue').textContent = e.target.value;
        });
        
        const topPSlider = document.getElementById('topP');
        topPSlider.addEventListener('input', (e) => {
            document.getElementById('topPValue').textContent = e.target.value;
        });
    }
    
    // API Communication Methods
    
    async loadStatus() {
        console.log("[DEBUG] Loading client status");
        
        try {
            const response = await fetch(`${this.apiBase}/api/status`);
            const data = await response.json();
            
            if (data.connected) {
                console.log("[DEBUG] Client connected, updating UI");
                this.updateConnectionStatus(true);
                this.updateModelDisplay(data.model);
                this.updateStreamingStatus(data.streaming);
                this.currentConversationId = data.conversation_id;
                
                if (data.conversation_name) {
                    document.getElementById('conversationName').textContent = data.conversation_name;
                }
                
                // Update settings form
                if (data.params) {
                    this.updateSettingsForm(data.params);
                }
            } else {
                console.log("[ERROR] Client not connected");
                this.updateConnectionStatus(false);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load status:", error);
            this.updateConnectionStatus(false);
        }
    }
    
    async loadConversations() {
        console.log("[DEBUG] Loading conversations list");
        
        try {
            const response = await fetch(`${this.apiBase}/api/conversations`);
            const data = await response.json();
            
            if (data.conversations) {
                console.log(`[DEBUG] Loaded ${data.conversations.length} conversations`);
                this.displayConversations(data.conversations);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load conversations:", error);
        }
    }
    
    async loadModels() {
        console.log("[DEBUG] Loading available models");
        
        try {
            const response = await fetch(`${this.apiBase}/api/models`);
            const data = await response.json();
            
            if (data.models) {
                console.log(`[DEBUG] Loaded ${data.models.length} models`);
                this.displayModels(data.models);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load models:", error);
            this.showAlert('Failed to load models', 'danger');
        }
    }
    
    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();
        
        if (!message) return;
        
        console.log(`[DEBUG] Sending message: ${message.substring(0, 50)}...`);
        
        // Check if it's a command
        if (message.startsWith('/')) {
            await this.handleCommand(message);
            messageInput.value = '';
            return;
        }
        
        // Add user message to chat
        this.addMessage('user', message);
        messageInput.value = '';
        
        // Show thinking indicator
        this.showThinking(true);
        
        try {
            if (this.streamingEnabled) {
                // Use Server-Sent Events for streaming
                await this.sendStreamingMessage(message);
            } else {
                // Regular request-response
                const response = await fetch(`${this.apiBase}/api/send`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    this.showAlert(data.error, 'danger');
                    this.addMessage('system', `Error: ${data.error}`);
                } else {
                    this.addMessage('assistant', data.response);
                    this.currentConversationId = data.conversation_id;
                }
            }
        } catch (error) {
            console.error("[ERROR] Failed to send message:", error);
            this.showAlert('Failed to send message', 'danger');
        } finally {
            this.showThinking(false);
        }
    }
    
    async sendStreamingMessage(message) {
        console.log("[DEBUG] Sending streaming message");
        
        // Create a temporary message element for streaming
        const tempMessageId = `msg-${Date.now()}`;
        this.addMessage('assistant', '', tempMessageId);
        
        const messageElement = document.getElementById(tempMessageId);
        let fullResponse = '';
        
        try {
            const response = await fetch(`${this.apiBase}/api/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.chunk) {
                                fullResponse += data.chunk;
                                messageElement.querySelector('.message-content').textContent = fullResponse;
                                // Auto-scroll to bottom
                                this.scrollToBottom();
                            } else if (data.done) {
                                console.log("[DEBUG] Streaming complete");
                                this.currentConversationId = data.conversation_id;
                            } else if (data.error) {
                                console.error("[ERROR] Streaming error:", data.error);
                                this.showAlert(data.error, 'danger');
                            }
                        } catch (e) {
                            console.error("[ERROR] Failed to parse SSE data:", e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error("[ERROR] Streaming failed:", error);
            this.showAlert('Streaming failed', 'danger');
        }
    }
    
    async handleCommand(command) {
        console.log(`[DEBUG] Handling command: ${command}`);
        
        // Handle special UI commands
        if (command === '/help') {
            this.showHelp();
            return;
        }
        
        // For other commands, send to backend
        try {
            const response = await fetch(`${this.apiBase}/api/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command })
            });
            
            const data = await response.json();
            
            if (data.error) {
                this.showAlert(data.error, 'danger');
            } else if (data.success) {
                // Reload relevant data based on command
                if (command.startsWith('/new') || command.startsWith('/load')) {
                    await this.loadStatus();
                    await this.loadConversations();
                    this.clearChat();
                }
            }
        } catch (error) {
            console.error("[ERROR] Command failed:", error);
            this.showAlert('Command failed', 'danger');
        }
    }
    
    // UI Update Methods
    
    displayConversations(conversations) {
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = '';
        
        conversations.forEach((conv, index) => {
            const li = document.createElement('li');
            li.className = 'nav-item';
            
            const createdDate = new Date(conv.created_at).toLocaleDateString();
            
            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" 
                   href="#" onclick="app.loadConversation('${conv.title}')">
                    <div>
                        <strong>${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count} messages • ${createdDate}</small>
                    </div>
                    <i class="bi bi-chevron-right"></i>
                </a>
            `;
            
            listElement.appendChild(li);
        });
    }
    
    displayModels(models) {
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = '';
        
        models.forEach(model => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${model.name}</code></td>
                <td>${model.display_name}</td>
                <td>${model.input_token_limit}</td>
                <td>${model.output_token_limit}</td>
                <td>
                    <button class="btn btn-sm btn-primary" 
                            onclick="app.selectModel('${model.name}')">
                        Select
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }
    
    async retryMessage(messageId) {
        console.log(`[DEBUG] Retrying message: ${messageId}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            console.log(`[DEBUG] Retry response:`, data);
            
            if (data.error) {
                this.showAlert(data.error, 'danger');
                return;
            }
            
            // Instead of adding the message below, we need to navigate to the new branch
            // The backend has already created the new message on a new branch
            await this.navigateSibling(data.message.id, 'none');
            
            this.showAlert('Generated new response', 'success');
        } catch (error) {
            console.error("[ERROR] Failed to retry message:", error);
            this.showAlert('Failed to retry message', 'danger');
        }
    }
    
    async navigateSibling(messageId, direction) {
        console.log(`[DEBUG] Navigating ${direction} from message: ${messageId}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/navigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, direction })
            });
            
            const data = await response.json();
            console.log(`[DEBUG] Navigation response:`, data);
            
            if (data.error) {
                this.showAlert(data.error, 'danger');
                return;
            }
            
            // Clear and rebuild the chat with the new branch
            this.clearChat();
            
            // Clear the message tree to rebuild it
            this.messageTree = {};
            
            // Display the updated conversation history
            if (data.history && data.history.length > 0) {
                // Build parent-child relationships first
                const messagesByParent = {};
                data.history.forEach(msg => {
                    if (msg.parent_id) {
                        if (!messagesByParent[msg.parent_id]) {
                            messagesByParent[msg.parent_id] = [];
                        }
                        messagesByParent[msg.parent_id].push(msg);
                    }
                });
                
                // Add messages and calculate sibling info
                data.history.forEach(msg => {
                    const siblings = msg.parent_id ? (messagesByParent[msg.parent_id] || []) : [];
                    const siblingIndex = siblings.findIndex(s => s.id === msg.id);
                    const totalSiblings = siblings.length;
                    
                    this.addMessage(
                        msg.role === 'user' ? 'user' : 'assistant', 
                        msg.content,
                        msg.id,
                        {
                            model: msg.model,
                            parent_id: msg.parent_id,
                            siblingIndex: siblingIndex >= 0 ? siblingIndex : 0,
                            totalSiblings: totalSiblings > 0 ? totalSiblings : 1
                        }
                    );
                });
                
                // Update all sibling indicators after loading
                this.updateAllSiblingIndicators();
            }
            
            // Update active leaf
            this.activeLeaf = data.message.id;
            
            // Only show alert if we're actually navigating between siblings
            if (direction !== 'none' && data.total_siblings > 1) {
                this.showAlert(`Switched to response ${data.sibling_index + 1} of ${data.total_siblings}`, 'info');
            }
        } catch (error) {
            console.error("[ERROR] Failed to navigate sibling:", error);
            this.showAlert('Failed to navigate to sibling', 'danger');
        }
    }
    
    async updateSiblingIndicators(parentId) {
        console.log(`[DEBUG] Updating sibling indicators for parent: ${parentId}`);
        
        // Get all messages with this parent
        const siblings = Object.values(this.messageTree).filter(msg => msg.parent_id === parentId);
        console.log(`[DEBUG] Found ${siblings.length} siblings`);
        
        siblings.forEach((sibling, index) => {
            const element = document.getElementById(sibling.id);
            if (element) {
                const indicator = element.querySelector('.branch-indicator');
                if (indicator) {
                    indicator.textContent = `${index + 1} of ${siblings.length}`;
                }
                
                // Update navigation buttons
                const prevBtn = element.querySelector('.btn-prev-sibling');
                const nextBtn = element.querySelector('.btn-next-sibling');
                
                if (prevBtn && nextBtn) {
                    // Show/hide based on siblings
                    if (siblings.length > 1) {
                        prevBtn.style.display = 'inline-block';
                        nextBtn.style.display = 'inline-block';
                    } else {
                        prevBtn.style.display = 'none';
                        nextBtn.style.display = 'none';
                    }
                }
            }
        });
    }
    
    updateAllSiblingIndicators() {
        console.log('[DEBUG] Updating all sibling indicators');
        
        // Get all unique parent IDs
        const parentIds = new Set();
        Object.values(this.messageTree).forEach(msg => {
            if (msg.parent_id) {
                parentIds.add(msg.parent_id);
            }
        });
        
        console.log(`[DEBUG] Found ${parentIds.size} unique parent IDs`);
        
        // Update indicators for each parent
        parentIds.forEach(parentId => {
            this.updateSiblingIndicators(parentId);
        });
    }
    
    addMessage(role, content, messageId = null, metadata = {}) {
        console.log(`[DEBUG] Adding message - Role: ${role}, ID: ${messageId}, Metadata:`, metadata);
        
        const chatMessages = document.getElementById('chatMessages');
        
        // Remove empty state message if it exists
        const emptyState = chatMessages.querySelector('.text-center');
        if (emptyState) {
            emptyState.remove();
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message-${role} mb-3`;
        if (messageId) {
            messageDiv.id = messageId;
            // Store message data in our tree with all metadata
            this.messageTree[messageId] = {
                id: messageId,
                role: role,
                content: content,
                parent_id: metadata.parent_id || null,
                ...metadata
            };
            this.messageElements[messageId] = messageDiv;
        }
        
        let icon, roleLabel, bgClass;
        switch (role) {
            case 'user':
                icon = 'bi-person-circle';
                roleLabel = 'You';
                bgClass = 'bg-primary text-white';
                break;
            case 'assistant':
                icon = 'bi-robot';
                roleLabel = 'Gemini';
                bgClass = 'bg-light';
                break;
            case 'system':
                icon = 'bi-info-circle';
                roleLabel = 'System';
                bgClass = 'bg-warning bg-opacity-25';
                break;
        }
        
        // Build header with metadata for assistant messages
        let headerContent = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && metadata.model) {
            headerContent += ` <span class="badge bg-secondary">${metadata.model}</span>`;
        }
        if (role === 'assistant' && metadata.totalSiblings > 1) {
            headerContent += ` <span class="branch-indicator badge bg-info">${metadata.siblingIndex + 1} of ${metadata.totalSiblings}</span>`;
        }
        headerContent += ` <span class="text-muted ms-2">${new Date().toLocaleTimeString()}</span>`;
        
        // Build message actions for assistant messages
        let messageActions = '';
        if (role === 'assistant' && messageId) {
            messageActions = `
                <div class="message-actions mt-2">
                    <button class="btn btn-sm btn-outline-secondary btn-retry" onclick="app.retryMessage('${messageId}')" title="Retry this response">
                        <i class="bi bi-arrow-clockwise"></i> Retry
                    </button>
                    <button class="btn btn-sm btn-outline-secondary btn-prev-sibling" onclick="app.navigateSibling('${messageId}', 'prev')" title="Previous response" style="display: none;">
                        <i class="bi bi-chevron-left"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary btn-next-sibling" onclick="app.navigateSibling('${messageId}', 'next')" title="Next response" style="display: none;">
                        <i class="bi bi-chevron-right"></i>
                    </button>
                </div>
            `;
        }
        
        messageDiv.innerHTML = `
            <div class="d-flex align-items-start">
                <div class="message-icon me-3">
                    <i class="bi ${icon} fs-4"></i>
                </div>
                <div class="message-body flex-grow-1">
                    <div class="message-header mb-1">
                        ${headerContent}
                    </div>
                    <div class="message-content ${bgClass} p-3 rounded">
                        ${this.formatMessage(content)}
                    </div>
                    ${messageActions}
                </div>
            </div>
        `;
        
        chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        // Update sibling navigation buttons if needed
        if (role === 'assistant' && metadata.totalSiblings > 1) {
            const prevBtn = messageDiv.querySelector('.btn-prev-sibling');
            const nextBtn = messageDiv.querySelector('.btn-next-sibling');
            if (prevBtn && nextBtn) {
                prevBtn.style.display = 'inline-block';
                nextBtn.style.display = 'inline-block';
            }
        }
    }
    
    formatMessage(content) {
        // Basic formatting - escape HTML and convert newlines to <br>
        const escaped = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
        
        return escaped.replace(/\n/g, '<br>');
    }
    
    clearChat() {
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-chat-dots display-1"></i>
                <p>Start a conversation by typing a message below</p>
            </div>
        `;
    }
    
    scrollToBottom() {
        const chatContainer = document.getElementById('chatContainer');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    
    showThinking(show) {
        const indicator = document.getElementById('thinkingIndicator');
        if (show) {
            indicator.classList.remove('d-none');
        } else {
            indicator.classList.add('d-none');
        }
    }
    
    updateConnectionStatus(connected = true) {
        const statusElement = document.getElementById('connectionStatus');
        if (connected) {
            statusElement.innerHTML = '<i class="bi bi-circle-fill text-success"></i> Connected';
        } else {
            statusElement.innerHTML = '<i class="bi bi-circle-fill text-danger"></i> Disconnected';
        }
    }
    
    updateModelDisplay(model) {
        document.getElementById('currentModel').textContent = model || 'Unknown';
    }
    
    updateStreamingStatus(enabled) {
        this.streamingEnabled = enabled;
        document.getElementById('streamingMode').textContent = enabled ? 'ON' : 'OFF';
        document.getElementById('streamingToggle').checked = enabled;
    }
    
    updateSettingsForm(params) {
        if (params.temperature !== undefined) {
            document.getElementById('temperature').value = params.temperature;
            document.getElementById('temperatureValue').textContent = params.temperature;
        }
        if (params.max_output_tokens !== undefined) {
            document.getElementById('maxTokens').value = params.max_output_tokens;
        }
        if (params.top_p !== undefined) {
            document.getElementById('topP').value = params.top_p;
            document.getElementById('topPValue').textContent = params.top_p;
        }
        if (params.top_k !== undefined) {
            document.getElementById('topK').value = params.top_k;
        }
    }
    
    // Modal and Action Methods
    
    showNewConversationModal() {
        console.log("[DEBUG] Showing new conversation modal");
        document.getElementById('conversationTitle').value = '';
        this.modals.newConversation.show();
    }
    
    async createNewConversation() {
        const title = document.getElementById('conversationTitle').value.trim();
        console.log(`[DEBUG] Creating new conversation: ${title || '(auto-generated)'}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/new`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.currentConversationId = data.conversation_id;
                document.getElementById('conversationName').textContent = data.conversation_name;
                this.clearChat();
                this.showAlert('New conversation started', 'success');
                this.modals.newConversation.hide();
                await this.loadConversations();
            } else {
                this.showAlert(data.error || 'Failed to create conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to create conversation:", error);
            this.showAlert('Failed to create conversation', 'danger');
        }
    }
    
    async loadConversation(conversationName) {
        console.log(`[DEBUG] Loading conversation: ${conversationName}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/load`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_name: conversationName })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.currentConversationId = data.conversation_id;
                document.getElementById('conversationName').textContent = data.conversation_name;
                this.clearChat();
                
                // Clear the message tree to rebuild it
                this.messageTree = {};
                
                // Display conversation history with proper metadata
                if (data.history && data.history.length > 0) {
                    console.log(`[DEBUG] Loading ${data.history.length} messages from history`);
                    
                    // Build parent-child relationships first
                    const messagesByParent = {};
                    data.history.forEach(msg => {
                        if (msg.parent_id) {
                            if (!messagesByParent[msg.parent_id]) {
                                messagesByParent[msg.parent_id] = [];
                            }
                            messagesByParent[msg.parent_id].push(msg);
                        }
                    });
                    
                    // Add messages with proper sibling info
                    data.history.forEach(msg => {
                        console.log(`[DEBUG] Loading message: ${msg.id}, role: ${msg.role}, parent: ${msg.parent_id}`);
                        
                        const siblings = msg.parent_id ? (messagesByParent[msg.parent_id] || []) : [];
                        const siblingIndex = siblings.findIndex(s => s.id === msg.id);
                        const totalSiblings = siblings.length;
                        
                        this.addMessage(
                            msg.role === 'user' ? 'user' : 'assistant', 
                            msg.content,
                            msg.id,
                            {
                                model: msg.model,
                                timestamp: msg.timestamp,
                                parent_id: msg.parent_id,
                                siblingIndex: siblingIndex >= 0 ? siblingIndex : 0,
                                totalSiblings: totalSiblings > 0 ? totalSiblings : 1
                            }
                        );
                    });
                    
                    // After loading, update sibling indicators for all messages
                    console.log('[DEBUG] Updating sibling indicators after load');
                    this.updateAllSiblingIndicators();
                } else {
                    this.showAlert('Conversation loaded (no messages)', 'info');
                }
            } else {
                this.showAlert(data.error || 'Failed to load conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to load conversation:", error);
            this.showAlert('Failed to load conversation', 'danger');
        }
    }
    
    async saveConversation() {
        console.log("[DEBUG] Saving conversation");
        
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showAlert('Conversation saved', 'success');
            } else {
                this.showAlert(data.error || 'Failed to save conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to save conversation:", error);
            this.showAlert('Failed to save conversation', 'danger');
        }
    }
    
    showModelSelector() {
        console.log("[DEBUG] Showing model selector");
        this.loadModels();
        this.modals.modelSelector.show();
    }
    
    async selectModel(modelName) {
        console.log(`[DEBUG] Selecting model: ${modelName}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelName })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.updateModelDisplay(data.model);
                this.showAlert(`Model changed to ${modelName}`, 'success');
                this.modals.modelSelector.hide();
            } else {
                this.showAlert(data.error || 'Failed to change model', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to change model:", error);
            this.showAlert('Failed to change model', 'danger');
        }
    }
    
    showSettings() {
        console.log("[DEBUG] Showing settings");
        this.modals.settings.show();
    }
    
    async saveSettings() {
        console.log("[DEBUG] Saving settings");
        
        const params = {
            temperature: parseFloat(document.getElementById('temperature').value),
            max_output_tokens: parseInt(document.getElementById('maxTokens').value),
            top_p: parseFloat(document.getElementById('topP').value),
            top_k: parseInt(document.getElementById('topK').value)
        };
        
        const streaming = document.getElementById('streamingToggle').checked;
        
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params, streaming })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.updateStreamingStatus(data.streaming);
                this.showAlert('Settings saved', 'success');
                this.modals.settings.hide();
            } else {
                this.showAlert(data.error || 'Failed to save settings', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to save settings:", error);
            this.showAlert('Failed to save settings', 'danger');
        }
    }
    
    async toggleStreaming() {
        const newState = !this.streamingEnabled;
        console.log(`[DEBUG] Toggling streaming to: ${newState}`);
        
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ streaming: newState })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.updateStreamingStatus(data.streaming);
                this.showAlert(`Streaming ${data.streaming ? 'enabled' : 'disabled'}`, 'success');
            }
        } catch (error) {
            console.error("[ERROR] Failed to toggle streaming:", error);
            this.showAlert('Failed to toggle streaming', 'danger');
        }
    }
    
    showHistory() {
        // This would typically show a more detailed history view
        // For now, we'll just show an alert
        this.showAlert('History is displayed in the main chat area', 'info');
    }
    
    showHelp() {
        const helpContent = `
            <h5>Available Commands</h5>
            <ul>
                <li><code>/new [title]</code> - Start a new conversation</li>
                <li><code>/save</code> - Save the current conversation</li>
                <li><code>/list</code> - List saved conversations</li>
                <li><code>/load [name/number]</code> - Load a conversation</li>
                <li><code>/history</code> - Show conversation history</li>
                <li><code>/model [name]</code> - Change the AI model</li>
                <li><code>/params</code> - Customize generation parameters</li>
                <li><code>/stream</code> - Toggle streaming mode</li>
                <li><code>/help</code> - Show this help message</li>
            </ul>
        `;
        
        this.addMessage('system', helpContent);
    }
    
    showAlert(message, type = 'info') {
        const alertContainer = document.getElementById('alertContainer');
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        alertContainer.appendChild(alertDiv);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Initialize the app
const app = new GeminiChatApp();
