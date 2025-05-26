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
        
        // App settings
        this.appSettings = this.loadAppSettings();
        
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
        this.modals.appSettings = new bootstrap.Modal(document.getElementById('appSettingsModal'));
        
        // Apply saved app settings
        this.applyAppSettings();
        
        // Configure marked.js for Markdown parsing
        marked.setOptions({
            highlight: function(code, lang) {
                if (lang && hljs.getLanguage(lang)) {
                    try {
                        return hljs.highlight(code, { language: lang }).value;
                    } catch (e) {
                        console.error('[ERROR] Highlight.js error:', e);
                    }
                }
                return hljs.highlightAuto(code).value;
            },
            breaks: true,
            gfm: true
        });
        
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
        
        // App settings form inputs
        const fontSizeSlider = document.getElementById('fontSize');
        fontSizeSlider.addEventListener('input', (e) => {
            document.getElementById('fontSizeValue').textContent = e.target.value;
            this.updatePreview();
        });
        
        // Theme radio buttons
        document.querySelectorAll('input[name="theme"]').forEach(radio => {
            radio.addEventListener('change', () => this.updatePreview());
        });
        
        // Font family select
        document.getElementById('fontFamily').addEventListener('change', () => this.updatePreview());
        
        // Code theme select
        document.getElementById('codeTheme').addEventListener('change', () => this.updatePreview());
        
        // Display settings checkboxes
        ['showTimestamps', 'showAvatars', 'enableAnimations', 'compactMode', 'showLineNumbers'].forEach(id => {
            document.getElementById(id).addEventListener('change', () => this.updatePreview());
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
        
        // Generate a temporary ID for the user message
        const userMessageId = `msg-user-${Date.now()}`;
        
        // Add user message to chat with ID
        this.addMessage('user', message, userMessageId);
        messageInput.value = '';
        
        // Store the current parent ID for the assistant message
        const parentMessageId = userMessageId;
        
        // Show thinking indicator
        this.showThinking(true);
        
        try {
            if (this.streamingEnabled) {
                // Use Server-Sent Events for streaming
                await this.sendStreamingMessage(message, parentMessageId);
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
                    console.log('[DEBUG] Got successful response from server');
                    console.log('[DEBUG] Response data:', data);
                    
                    // Extract message details from response if available
                    const messageId = data.message_id || `msg-assistant-${Date.now()}`;
                    const parentId = data.parent_id || parentMessageId;
                    
                    console.log(`[DEBUG] Message IDs - Assistant: ${messageId}, Parent: ${parentId}`);
                    
                    this.addMessage('assistant', data.response, messageId, {
                        model: data.model || this.currentModel,
                        parent_id: parentId
                    });
                    this.currentConversationId = data.conversation_id;
                    
                    // Ensure parent has this child in its children list
                    if (parentId && this.messageTree[parentId]) {
                        if (!this.messageTree[parentId].children) {
                            this.messageTree[parentId].children = [];
                        }
                        if (!this.messageTree[parentId].children.includes(messageId)) {
                            this.messageTree[parentId].children.push(messageId);
                            console.log(`[DEBUG] Added ${messageId} to parent ${parentId} children list`);
                        }
                    }
                    
                    // Update sibling indicators after a short delay
                    setTimeout(() => {
                        console.log(`[DEBUG] Updating sibling indicators for parent: ${parentId}`);
                        this.updateSiblingIndicators(parentId);
                    }, 100);
                }
            }
        } catch (error) {
            console.error("[ERROR] Failed to send message:", error);
            this.showAlert('Failed to send message', 'danger');
        } finally {
            this.showThinking(false);
        }
    }
    
    async sendStreamingMessage(message, parentMessageId) {
        console.log("[DEBUG] Sending streaming message with parent:", parentMessageId);
        
        // Create a temporary message element for streaming
        const tempMessageId = `msg-${Date.now()}`;
        this.addMessage('assistant', '', tempMessageId, {
            parent_id: parentMessageId
        });
        
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
                                
                                // Update message with proper IDs and metadata
                                console.log('[DEBUG] Streaming complete with data:', data);
                                
                                // Update message ID if provided
                                const finalMessageId = data.message_id || tempMessageId;
                                const finalParentId = data.parent_id || parentMessageId;
                                
                                console.log(`[DEBUG] Final message IDs - Assistant: ${finalMessageId}, Parent: ${finalParentId}`);
                                
                                if (finalMessageId !== tempMessageId) {
                                    messageElement.id = finalMessageId;
                                }
                                
                                // Update message tree with final data
                                this.messageTree[finalMessageId] = {
                                    id: finalMessageId,
                                    role: 'assistant',
                                    content: fullResponse,
                                    parent_id: finalParentId,
                                    model: data.model || this.currentModel
                                };
                                
                                // Ensure parent has this child in its children list
                                if (finalParentId && this.messageTree[finalParentId]) {
                                    if (!this.messageTree[finalParentId].children) {
                                        this.messageTree[finalParentId].children = [];
                                    }
                                    if (!this.messageTree[finalParentId].children.includes(finalMessageId)) {
                                        this.messageTree[finalParentId].children.push(finalMessageId);
                                        console.log(`[DEBUG] Added ${finalMessageId} to parent ${finalParentId} children list`);
                                    }
                                    
                                    // Update sibling indicators
                                    setTimeout(() => {
                                        console.log(`[DEBUG] Updating sibling indicators for parent: ${finalParentId}`);
                                        this.updateSiblingIndicators(finalParentId);
                                    }, 100);
                                }
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
            
            // Store the parent ID before navigation (which clears the chat)
            const parentId = data.message.parent_id;
            console.log(`[DEBUG] Parent ID for sibling update: ${parentId}`);
            
            // Navigate to show the new message in context
            await this.navigateSibling(data.message.id, 'none');
            
            // Force update of sibling indicators after a delay to ensure DOM is ready
            setTimeout(() => {
                console.log(`[DEBUG] Force updating sibling indicators after retry`);
                // Update all messages with the same parent
                if (parentId && this.messageTree[parentId] && this.messageTree[parentId].children) {
                    console.log(`[DEBUG] Updating indicators for ${this.messageTree[parentId].children.length} siblings`);
                    this.updateSiblingIndicators(parentId);
                    
                    // Also ensure the navigation buttons are visible for all siblings
                    this.messageTree[parentId].children.forEach(childId => {
                        const element = document.getElementById(childId);
                        if (element) {
                            const prevBtn = element.querySelector('.btn-prev-sibling');
                            const nextBtn = element.querySelector('.btn-next-sibling');
                            if (prevBtn && nextBtn && this.messageTree[parentId].children.length > 1) {
                                prevBtn.style.display = 'inline-block';
                                nextBtn.style.display = 'inline-block';
                                console.log(`[DEBUG] Made nav buttons visible for message ${childId}`);
                            }
                        }
                    });
                }
            }, 200);
            
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
                // First pass: Create all messages in the tree
                data.history.forEach(msg => {
                    this.messageTree[msg.id] = {
                        id: msg.id,
                        role: msg.role,
                        content: msg.content,
                        parent_id: msg.parent_id,
                        model: msg.model,
                        children: []
                    };
                });
                
                // Second pass: Build parent-child relationships
                data.history.forEach(msg => {
                    if (msg.parent_id && this.messageTree[msg.parent_id]) {
                        if (!this.messageTree[msg.parent_id].children.includes(msg.id)) {
                            this.messageTree[msg.parent_id].children.push(msg.id);
                        }
                    }
                });
                
                // Log the tree structure for debugging
                console.log('[DEBUG] Message tree after navigation:', this.messageTree);
                
                // Third pass: Add messages to DOM with proper sibling info
                data.history.forEach(msg => {
                    let siblingIndex = 0;
                    let totalSiblings = 1;
                    
                    if (msg.parent_id && this.messageTree[msg.parent_id]) {
                        const siblings = this.messageTree[msg.parent_id].children;
                        totalSiblings = siblings.length;
                        siblingIndex = siblings.indexOf(msg.id);
                        if (siblingIndex === -1) siblingIndex = 0;
                    }
                    
                    this.addMessage(
                        msg.role === 'user' ? 'user' : 'assistant', 
                        msg.content,
                        msg.id,
                        {
                            model: msg.model,
                            parent_id: msg.parent_id,
                            siblingIndex: siblingIndex,
                            totalSiblings: totalSiblings
                        }
                    );
                });
                
                // Update all sibling indicators after loading
                setTimeout(() => {
                    console.log('[DEBUG] Updating all sibling indicators after navigation');
                    this.updateAllSiblingIndicators();
                }, 100);
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
        
        // Get parent message to find children
        const parent = this.messageTree[parentId];
        if (!parent || !parent.children) {
            console.log(`[DEBUG] No parent or children found for ${parentId}`);
            return;
        }
        
        const siblings = parent.children;
        console.log(`[DEBUG] Found ${siblings.length} siblings from parent's children list:`, siblings);
        
        siblings.forEach((siblingId, index) => {
            const element = document.getElementById(siblingId);
            if (element) {
                console.log(`[DEBUG] Updating sibling ${siblingId} (${index + 1} of ${siblings.length})`);
                
                // Update or create the indicator
                let indicator = element.querySelector('.branch-indicator');
                if (!indicator && siblings.length > 1) {
                    // Create indicator if it doesn't exist
                    const header = element.querySelector('.message-header');
                    if (header) {
                        const newIndicator = document.createElement('span');
                        newIndicator.className = 'branch-indicator badge bg-info';
                        newIndicator.textContent = `${index + 1} of ${siblings.length}`;
                        // Insert after the model badge or after the role label
                        const modelBadge = header.querySelector('.badge.bg-secondary');
                        if (modelBadge) {
                            modelBadge.insertAdjacentElement('afterend', document.createTextNode(' '));
                            modelBadge.insertAdjacentElement('afterend', newIndicator);
                        } else {
                            const strong = header.querySelector('strong');
                            if (strong) {
                                strong.insertAdjacentElement('afterend', document.createTextNode(' '));
                                strong.insertAdjacentElement('afterend', newIndicator);
                            }
                        }
                        console.log(`[DEBUG] Created new branch indicator for ${siblingId}`);
                    }
                } else if (indicator) {
                    indicator.textContent = `${index + 1} of ${siblings.length}`;
                    console.log(`[DEBUG] Updated existing branch indicator for ${siblingId}`);
                }
                
                // Update navigation buttons visibility
                const messageActions = element.querySelector('.message-actions');
                if (messageActions) {
                    const prevBtn = messageActions.querySelector('.btn-prev-sibling');
                    const nextBtn = messageActions.querySelector('.btn-next-sibling');
                    
                    if (prevBtn && nextBtn) {
                        // Show/hide based on siblings
                        if (siblings.length > 1) {
                            prevBtn.style.display = 'inline-block';
                            nextBtn.style.display = 'inline-block';
                            console.log(`[DEBUG] Made navigation buttons visible for ${siblingId}`);
                        } else {
                            prevBtn.style.display = 'none';
                            nextBtn.style.display = 'none';
                            console.log(`[DEBUG] Hid navigation buttons for ${siblingId} (no siblings)`);
                        }
                    } else {
                        console.log(`[DEBUG] No navigation buttons found for ${siblingId}`);
                    }
                } else {
                    console.log(`[DEBUG] No message-actions div found for ${siblingId}`);
                }
            } else {
                console.log(`[DEBUG] Element not found for sibling ${siblingId}`);
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
        
        // Calculate actual sibling info if not provided
        let actualSiblings = 1;
        let actualIndex = 0;
        if (role === 'assistant' && messageId && metadata.parent_id) {
            const parent = this.messageTree[metadata.parent_id];
            if (parent && parent.children) {
                actualSiblings = parent.children.length;
            actualIndex = parent.children.indexOf(messageId);
        if (actualIndex === -1) actualIndex = 0;
        }
        }
        
        // Show sibling indicator if there are multiple siblings
        if (role === 'assistant' && actualSiblings > 1) {
        headerContent += ` <span class="branch-indicator badge bg-info">${actualIndex + 1} of ${actualSiblings}</span>`;
        }
        headerContent += ` <span class="text-muted ms-2">${new Date().toLocaleTimeString()}</span>`;
        
        // Build message actions for assistant messages
        let messageActions = '';
        if (role === 'assistant' && messageId) {
                const showNavButtons = actualSiblings > 1 ? 'inline-block' : 'none';
                messageActions = `
                    <div class="message-actions mt-2">
                        <button class="btn btn-sm btn-outline-secondary btn-retry" onclick="app.retryMessage('${messageId}')" title="Retry this response">
                            <i class="bi bi-arrow-clockwise"></i> Retry
                        </button>
                        <button class="btn btn-sm btn-outline-secondary btn-prev-sibling" onclick="app.navigateSibling('${messageId}', 'prev')" title="Previous response" style="display: ${showNavButtons};">
                            <i class="bi bi-chevron-left"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-secondary btn-next-sibling" onclick="app.navigateSibling('${messageId}', 'next')" title="Next response" style="display: ${showNavButtons};">
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
        
        // Apply highlight.js to code blocks
        messageDiv.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
        
        this.scrollToBottom();
        
        // Ensure parent-child relationships are updated if this is a new assistant message
        if (role === 'assistant' && messageId && metadata.parent_id) {
            console.log(`[DEBUG] New assistant message added, updating parent-child relationships`);
            console.log(`[DEBUG] Message ID: ${messageId}, Parent ID: ${metadata.parent_id}`);
            
            // Update sibling indicators after adding the message
            setTimeout(() => {
                this.updateSiblingIndicators(metadata.parent_id);
                
                // Also re-render the action buttons if siblings exist
                const parent = this.messageTree[metadata.parent_id];
                if (parent && parent.children && parent.children.length > 1) {
                    console.log(`[DEBUG] Parent has ${parent.children.length} children, showing nav buttons`);
                    const prevBtn = messageDiv.querySelector('.btn-prev-sibling');
                    const nextBtn = messageDiv.querySelector('.btn-next-sibling');
                    if (prevBtn && nextBtn) {
                        prevBtn.style.display = 'inline-block';
                        nextBtn.style.display = 'inline-block';
                    }
                }
            }, 100);
        }
    }
    
    formatMessage(content) {
        console.log('[DEBUG] Formatting message with Markdown');
        
        try {
            // Parse markdown to HTML
            const html = marked.parse(content);
            
            // If line numbers are enabled, add them to code blocks
            if (this.appSettings.showLineNumbers) {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;
                
                tempDiv.querySelectorAll('pre code').forEach(block => {
                    const lines = block.textContent.split('\n');
                    const numberedLines = lines.map((line, i) => {
                        const lineNum = String(i + 1).padStart(3, ' ');
                        return `<span class="line-number">${lineNum}</span>${line}`;
                    }).join('\n');
                    
                    block.innerHTML = numberedLines;
                    block.classList.add('line-numbers');
                });
                
                return tempDiv.innerHTML;
            }
            
            return html;
        } catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error);
            // Fallback to basic formatting
            const escaped = content
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
            
            return escaped.replace(/\n/g, '<br>');
        }
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
    
    // App Settings Methods
    
    loadAppSettings() {
        console.log('[DEBUG] Loading app settings from localStorage');
        
        const defaults = {
            theme: 'light',
            fontSize: 16,
            fontFamily: 'system-ui',
            showTimestamps: true,
            showAvatars: true,
            enableAnimations: true,
            compactMode: false,
            codeTheme: 'github-dark',
            showLineNumbers: true
        };
        
        try {
            const saved = localStorage.getItem('geminiChatAppSettings');
            if (saved) {
                const settings = JSON.parse(saved);
                console.log('[DEBUG] Loaded saved settings:', settings);
                return { ...defaults, ...settings };
            }
        } catch (error) {
            console.error('[ERROR] Failed to load app settings:', error);
        }
        
        console.log('[DEBUG] Using default settings');
        return defaults;
    }
    
    saveAppSettingsToStorage() {
        console.log('[DEBUG] Saving app settings to localStorage');
        
        try {
            localStorage.setItem('geminiChatAppSettings', JSON.stringify(this.appSettings));
            console.log('[DEBUG] Settings saved successfully');
            return true;
        } catch (error) {
            console.error('[ERROR] Failed to save app settings:', error);
            return false;
        }
    }
    
    applyAppSettings() {
        console.log('[DEBUG] Applying app settings');
        
        // Apply theme
        this.applyTheme(this.appSettings.theme);
        
        // Apply font settings
        document.documentElement.style.setProperty('--chat-font-size', `${this.appSettings.fontSize}px`);
        document.documentElement.style.setProperty('--chat-font-family', this.appSettings.fontFamily);
        
        // Apply display settings
        document.body.classList.toggle('hide-timestamps', !this.appSettings.showTimestamps);
        document.body.classList.toggle('hide-avatars', !this.appSettings.showAvatars);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        
        // Update code theme
        this.updateCodeTheme(this.appSettings.codeTheme);
        
        console.log('[DEBUG] App settings applied');
    }
    
    applyTheme(theme) {
        console.log(`[DEBUG] Applying theme: ${theme}`);
        
        // Remove all theme classes
        document.body.classList.remove('theme-light', 'theme-dark', 'theme-auto');
        
        if (theme === 'auto') {
            // Check system preference
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            document.body.classList.add(prefersDark ? 'theme-dark' : 'theme-light');
        } else {
            document.body.classList.add(`theme-${theme}`);
        }
    }
    
    updateCodeTheme(theme) {
        console.log(`[DEBUG] Updating code theme to: ${theme}`);
        
        // Find the highlight.js CSS link
        const link = document.querySelector('link[href*="highlight.js"]');
        if (link) {
            const newHref = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${theme}.min.css`;
            link.href = newHref;
        }
    }
    
    showAppSettings() {
        console.log('[DEBUG] Showing app settings modal');
        
        // Update form with current settings
        document.getElementById(`theme${this.appSettings.theme.charAt(0).toUpperCase() + this.appSettings.theme.slice(1)}`).checked = true;
        document.getElementById('fontSize').value = this.appSettings.fontSize;
        document.getElementById('fontSizeValue').textContent = this.appSettings.fontSize;
        document.getElementById('fontFamily').value = this.appSettings.fontFamily;
        document.getElementById('showTimestamps').checked = this.appSettings.showTimestamps;
        document.getElementById('showAvatars').checked = this.appSettings.showAvatars;
        document.getElementById('enableAnimations').checked = this.appSettings.enableAnimations;
        document.getElementById('compactMode').checked = this.appSettings.compactMode;
        document.getElementById('codeTheme').value = this.appSettings.codeTheme;
        document.getElementById('showLineNumbers').checked = this.appSettings.showLineNumbers;
        
        // Update preview
        this.updatePreview();
        
        // Show modal
        this.modals.appSettings.show();
    }
    
    saveAppSettings() {
        console.log('[DEBUG] Saving app settings from form');
        
        // Get values from form
        this.appSettings = {
            theme: document.querySelector('input[name="theme"]:checked').value,
            fontSize: parseInt(document.getElementById('fontSize').value),
            fontFamily: document.getElementById('fontFamily').value,
            showTimestamps: document.getElementById('showTimestamps').checked,
            showAvatars: document.getElementById('showAvatars').checked,
            enableAnimations: document.getElementById('enableAnimations').checked,
            compactMode: document.getElementById('compactMode').checked,
            codeTheme: document.getElementById('codeTheme').value,
            showLineNumbers: document.getElementById('showLineNumbers').checked
        };
        
        // Save to localStorage
        if (this.saveAppSettingsToStorage()) {
            // Apply settings
            this.applyAppSettings();
            
            // Re-render all messages to apply new formatting
            this.reRenderAllMessages();
            
            // Show success message
            this.showAlert('App settings saved successfully', 'success');
            
            // Close modal
            this.modals.appSettings.hide();
        } else {
            this.showAlert('Failed to save app settings', 'danger');
        }
    }
    
    resetAppSettings() {
        console.log('[DEBUG] Resetting app settings to defaults');
        
        if (confirm('Are you sure you want to reset all app settings to defaults?')) {
            // Clear saved settings
            localStorage.removeItem('geminiChatAppSettings');
            
            // Reload defaults
            this.appSettings = this.loadAppSettings();
            
            // Apply defaults
            this.applyAppSettings();
            
            // Update form
            this.showAppSettings();
            
            // Re-render messages
            this.reRenderAllMessages();
            
            this.showAlert('App settings reset to defaults', 'info');
        }
    }
    
    updatePreview() {
        console.log('[DEBUG] Updating settings preview');
        
        const preview = document.getElementById('settingsPreview');
        
        // Get current form values
        const fontSize = document.getElementById('fontSize').value;
        const fontFamily = document.getElementById('fontFamily').value;
        const showTimestamps = document.getElementById('showTimestamps').checked;
        const showAvatars = document.getElementById('showAvatars').checked;
        const theme = document.querySelector('input[name="theme"]:checked').value;
        
        // Apply styles to preview
        preview.style.fontSize = `${fontSize}px`;
        preview.style.fontFamily = fontFamily;
        
        // Toggle visibility
        const avatar = preview.querySelector('#previewAvatar');
        const timestamp = preview.querySelector('#previewTimestamp');
        
        if (avatar) avatar.style.display = showAvatars ? 'block' : 'none';
        if (timestamp) timestamp.style.display = showTimestamps ? 'inline' : 'none';
        
        // Update theme class
        preview.className = `preview-area border rounded p-3 theme-${theme}`;
        
        // Re-highlight code in preview
        preview.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }
    
    reRenderAllMessages() {
        console.log('[DEBUG] Re-rendering all messages with new settings');
        
        // Get all message elements
        const messages = document.querySelectorAll('.message');
        
        messages.forEach(messageEl => {
            const messageId = messageEl.id;
            if (messageId && this.messageTree[messageId]) {
                const messageData = this.messageTree[messageId];
                
                // Find and update the message content
                const contentEl = messageEl.querySelector('.message-content');
                if (contentEl && messageData.content) {
                    contentEl.innerHTML = this.formatMessage(messageData.content);
                    
                    // Re-highlight code blocks
                    contentEl.querySelectorAll('pre code').forEach(block => {
                        hljs.highlightElement(block);
                    });
                }
                
                // Update timestamp visibility
                const timestampEl = messageEl.querySelector('.text-muted');
                if (timestampEl) {
                    timestampEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';
                }
                
                // Update avatar visibility
                const avatarEl = messageEl.querySelector('.message-icon');
                if (avatarEl) {
                    avatarEl.style.display = this.appSettings.showAvatars ? 'block' : 'none';
                }
            }
        });
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
