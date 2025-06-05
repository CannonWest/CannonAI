/**
 * CannonAI GUI - Frontend JavaScript
 * Handles all UI interactions and communication with the Flask backend
 */

class CannonAIApp {
    constructor() {
        console.log("[DEBUG] Initializing CannonAIApp");

        this.apiBase = window.location.origin;
        this.currentConversationId = null;
        this.streamingEnabled = false; // Server's master streaming setting (session default)
        this.currentSystemInstruction = "You are a helpful assistant."; // Default, updated from server/conversation
        this.currentModelName = null; // Will be updated from /api/status

        this.modals = {};
        this.appSettings = this.loadAppSettings();
        this.messageTree = {}; // Stores the full message tree for the current conversation
        this.messageElements = {}; // Maps message IDs to their DOM elements

        this.mainContentDefaultClasses = ['col-md-9', 'col-lg-10']; // Used if right sidebar is closed
        this.mainContentRightSidebarOpenClasses = ['col-md-6', 'col-lg-8']; // Used if right sidebar is open
        this.rightSidebarOpen = true; // Default state of the right sidebar

        // Store for model capabilities, e.g., { "gemini-2.0-flash": { output_token_limit: 8192, input_token_limit: ... }, ... }
        this.modelCapabilities = {};
        this.DEFAULT_MODEL_MAX_TOKENS = 8192; // Fallback if model specific limit not found
        this.MIN_OUTPUT_TOKENS = 128;        // Min value for the slider/input
        this.TOKEN_SLIDER_STEP = 128;        // Step for the slider

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }

    init() {
        console.log("[DEBUG] DOM ready, initializing app");

        this.modals.newConversation = new bootstrap.Modal(document.getElementById('newConversationModal'));
        this.modals.modelSelector = new bootstrap.Modal(document.getElementById('modelSelectorModal'));
        this.modals.appSettings = new bootstrap.Modal(document.getElementById('appSettingsModal'));
        const systemInstructionModalEl = document.getElementById('systemInstructionModal');
        if (systemInstructionModalEl) {
            this.modals.systemInstruction = new bootstrap.Modal(systemInstructionModalEl);
        } else {
            console.warn("[WARN] System Instruction Modal element not found during init.");
        }


        const mainContent = document.getElementById('mainContent');
        if (this.rightSidebarOpen) {
            mainContent.classList.remove(...this.mainContentDefaultClasses);
            mainContent.classList.add(...this.mainContentRightSidebarOpenClasses);
        }

        this.applyAppSettings();

        marked.setOptions({
            highlight: function(code, lang) {
                const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                try {
                    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
                } catch (e) {
                    console.error('[ERROR] Highlight.js error:', e);
                    return hljs.highlightAuto(code).value;
                }
            },
            breaks: true,
            gfm: true
        });

        this.setupEventListeners();
        this.loadInitialData(); // This will call loadStatus, which then calls updateModelSettingsSidebarForm
        setInterval(() => this.updateConnectionStatusOnly(), 10000);
        this.initTextareaAutoResize();
    }

    initTextareaAutoResize() {
        const textarea = document.getElementById('messageInput');
        if (!textarea) return;
        const initialHeight = textarea.offsetHeight > 0 ? textarea.offsetHeight : 40; // Use 40 as a fallback
        textarea.style.minHeight = `${initialHeight}px`;

        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto'; // Reset height to auto to get the scrollHeight
            let newHeight = textarea.scrollHeight;
            const maxHeight = 150; // Max height in pixels before textarea starts scrolling

            if (newHeight > maxHeight) {
                newHeight = maxHeight;
                textarea.style.overflowY = 'auto'; // Enable scrollbar
            } else {
                textarea.style.overflowY = 'hidden'; // Hide scrollbar
            }
            textarea.style.height = `${newHeight}px`;
        });
    }

    async loadInitialData() {
        await this.loadModels(); // Load model capabilities first
        await this.loadStatus(); // Then load current status which uses model capabilities
        await this.loadConversations();
    }

    setupEventListeners() {
        console.log("[DEBUG] Setting up event listeners");
        const messageInput = document.getElementById('messageInput');
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Temperature Slider
        const tempSlider = document.getElementById('temperatureInput');
        if (tempSlider) {
            tempSlider.addEventListener('input', (e) => {
                const display = document.getElementById('temperatureValueDisplay');
                if(display) display.textContent = parseFloat(e.target.value).toFixed(2); // show 2 decimal places
            });
        }

        // Top-P Slider
        const topPSlider = document.getElementById('topPInput');
        if (topPSlider) {
            topPSlider.addEventListener('input', (e) => {
                 const display = document.getElementById('topPValueDisplay');
                if(display) display.textContent = parseFloat(e.target.value).toFixed(2); // show 2 decimal places
            });
        }

        // Max Tokens Slider & Input
        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');
        const maxTokensValueDisplay = document.getElementById('maxTokensValueDisplay');

        if (maxTokensSlider && maxTokensInput && maxTokensValueDisplay) {
            maxTokensSlider.addEventListener('input', () => {
                const val = parseInt(maxTokensSlider.value);
                maxTokensInput.value = val;
                maxTokensValueDisplay.textContent = val;
            });
            maxTokensInput.addEventListener('input', () => {
                let val = parseInt(maxTokensInput.value);
                const min = parseInt(maxTokensSlider.min);
                const max = parseInt(maxTokensSlider.max);
                if (isNaN(val)) val = min;
                if (val < min) val = min;
                if (val > max) val = max;

                maxTokensInput.value = val; // Corrected value
                maxTokensSlider.value = val;
                maxTokensValueDisplay.textContent = val;
            });
             maxTokensInput.addEventListener('blur', () => { // Ensure step alignment on blur
                let val = parseInt(maxTokensInput.value);
                const step = parseInt(maxTokensSlider.step);
                const min = parseInt(maxTokensSlider.min);
                if (!isNaN(val) && !isNaN(step) && step > 0) {
                    val = Math.round((val - min) / step) * step + min;
                     if (val < min) val = min; // ensure it does not go below min after step alignment
                    const max = parseInt(maxTokensSlider.max);
                    if (val > max) val = max;

                    maxTokensInput.value = val;
                    maxTokensSlider.value = val;
                    maxTokensValueDisplay.textContent = val;
                }
            });
        }


        // App Settings Modal Listeners
        document.getElementById('fontSize')?.addEventListener('input', (e) => {
            const display = document.getElementById('fontSizeValue');
            if(display) display.textContent = e.target.value;
            this.updatePreview();
        });
        document.querySelectorAll('input[name="theme"]')?.forEach(radio => {
            radio.addEventListener('change', () => this.updatePreview());
        });
        document.getElementById('fontFamily')?.addEventListener('change', () => this.updatePreview());
        document.getElementById('codeTheme')?.addEventListener('change', () => this.updatePreview());
        ['showTimestamps', 'showAvatars', 'enableAnimations', 'compactMode', 'showLineNumbers'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.updatePreview());
        });

        // Conversation list actions (delegated)
        const conversationsList = document.getElementById('conversationsList');
        if (conversationsList) {
            conversationsList.addEventListener('click', (event) => {
                const button = event.target.closest('.three-dots-btn');
                if (button) {
                    event.stopPropagation(); // Prevent click from propagating to parent elements
                    const dropdown = button.nextElementSibling;
                    // Hide other open dropdowns
                    document.querySelectorAll('.conversation-item-dropdown.show').forEach(d => {
                        if (d !== dropdown) d.classList.remove('show');
                    });
                    document.querySelectorAll('.three-dots-btn.active').forEach(b => {
                        if (b !== button) { b.classList.remove('active'); b.setAttribute('aria-expanded', 'false'); }
                    });
                    // Toggle current dropdown
                    const isCurrentlyShown = dropdown.classList.contains('show');
                    dropdown.classList.toggle('show', !isCurrentlyShown);
                    button.classList.toggle('active', !isCurrentlyShown);
                    button.setAttribute('aria-expanded', String(!isCurrentlyShown));
                }
            });
        }
        // Global click listener to close dropdowns when clicking outside
        document.addEventListener('click', (event) => {
            if (!event.target.closest('.conversation-actions-menu')) {
                document.querySelectorAll('.conversation-item-dropdown.show').forEach(d => d.classList.remove('show'));
                document.querySelectorAll('.three-dots-btn.active').forEach(b => {
                    b.classList.remove('active'); b.setAttribute('aria-expanded', 'false');
                });
            }
        });
    }

    _rebuildMessageTreeRelationships() {
        // This function ensures parent-child relationships in this.messageTree are correct.
        if (Object.keys(this.messageTree).length === 0) return;

        // Initialize children arrays if they don't exist
        for (const msgId in this.messageTree) {
            if (!this.messageTree[msgId].children || !Array.isArray(this.messageTree[msgId].children)) {
                this.messageTree[msgId].children = [];
            }
        }
        // Populate children arrays based on parent_id
        for (const msgId in this.messageTree) {
            const messageNode = this.messageTree[msgId];
            if (messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                const parentNode = this.messageTree[messageNode.parent_id];
                if (!Array.isArray(parentNode.children)) parentNode.children = []; // Should be initialized above, but defensive
                if (!parentNode.children.includes(msgId)) {
                    parentNode.children.push(msgId);
                }
            }
        }
    }

    async loadStatus() {
        console.log("[DEBUG] Loading client status");
        try {
            const response = await fetch(`${this.apiBase}/api/status`);
            const data = await response.json();
            this.updateConnectionStatus(data.connected);

            if (data.connected) {
                this.currentModelName = data.model; // Store current model name
                this.updateModelDisplay(data.model);
                this.streamingEnabled = data.streaming; // Server's default streaming for session
                this.updateStreamingStatusDisplay(this.streamingEnabled); // Update based on session default

                this.currentSystemInstruction = data.system_instruction || "You are a helpful assistant.";

                // Update the right sidebar (including the new Max Tokens slider)
                // data.params contains the conversation-specific or session-specific params
                // data.streaming contains the conversation-specific or session-specific streaming preference
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction);
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);

                this.currentConversationId = data.conversation_id;
                if (data.conversation_id && data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships();
                } else if (!data.conversation_id) {
                    this.messageTree = {}; // Clear tree if no active conversation
                }
                const convNameEl = document.getElementById('conversationName');
                if (convNameEl) convNameEl.textContent = data.conversation_name || 'New Conversation';

                if (data.history && Array.isArray(data.history)) {
                    this.rebuildChatFromHistory(data.history);
                } else {
                    this.clearChatDisplay(); // Clear display if no history
                }
            } else {
                // Handle disconnected state
                this.currentModelName = null;
                this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
                this.updateModelSettingsSidebarForm({}, false, this.currentSystemInstruction); // Reset sidebar with defaults
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load status:", error);
            this.updateConnectionStatus(false);
            this.currentModelName = null;
            this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
            this.updateModelSettingsSidebarForm({}, false, this.currentSystemInstruction);
            this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
        }
    }

    updateConnectionStatusOnly() {
        fetch(`${this.apiBase}/api/status`)
            .then(response => response.json())
            .then(data => this.updateConnectionStatus(data.connected))
            .catch(() => this.updateConnectionStatus(false));
    }

    async loadConversations() {
        console.log("[DEBUG] Loading conversations list");
        try {
            const response = await fetch(`${this.apiBase}/api/conversations`);
            const data = await response.json();
            if (data.conversations) this.displayConversationsList(data.conversations);
        } catch (error) { console.error("[ERROR] Failed to load conversations:", error); }
    }

    async loadModels() {
        console.log("[DEBUG] Loading available models");
        try {
            const response = await fetch(`${this.apiBase}/api/models`);
            const data = await response.json();
            if (data.models && Array.isArray(data.models)) {
                this.modelCapabilities = {}; // Clear previous
                data.models.forEach(model => {
                    this.modelCapabilities[model.name] = {
                        output_token_limit: model.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS,
                        input_token_limit: model.input_token_limit || 0 // Or some other fallback
                        // Store other capabilities if needed
                    };
                });
                this.displayModelsList(data.models);
            } else {
                this.modelCapabilities = {}; // Clear if no models
            }
        } catch (error) {
            console.error("[ERROR] Failed to load models:", error);
            this.showAlert('Failed to load models', 'danger');
            this.modelCapabilities = {}; // Clear on error
        }
    }

    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const messageContent = messageInput.value.trim();
        if (!messageContent) return;

        if (messageContent.startsWith('/')) {
            await this.handleCommand(messageContent);
            messageInput.value = ''; messageInput.style.height = 'auto'; return;
        }

        // Use the streaming preference from the right sidebar toggle for this send action
        const clientRequestsStreaming = document.getElementById('streamingToggleRightSidebar').checked;
        console.log(`[DEBUG] Sending message. Client requests streaming: ${clientRequestsStreaming}`);


        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const parentIdForNewMessage = this.getLastMessageIdFromActiveBranchDOM();
        this.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentIdForNewMessage });
        messageInput.value = ''; messageInput.style.height = 'auto'; // Reset textarea
        this.showThinking(true);

        const endpoint = clientRequestsStreaming ? `${this.apiBase}/api/stream` : `${this.apiBase}/api/send`;

        try {
            if (clientRequestsStreaming) { // Streaming
                let fullResponseText = "";
                const response = await fetch(endpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: messageContent })
                });
                if (!response.ok || !response.body) throw new Error(`Streaming request failed: ${response.statusText}`);

                const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
                this.showThinking(false);
                let tempAssistantMessageId = `msg-assistant-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
                this.addMessageToDOM('assistant', '...', tempAssistantMessageId, { parent_id: tempUserMessageId, model: "Streaming..." });

                while (true) {
                    const { value, done } = await reader.read(); if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    let boundary = buffer.indexOf("\n\n"); // SSE event boundary
                    while (boundary !== -1) {
                        const chunkDataString = buffer.substring(0, boundary).replace(/^data: /, '');
                        buffer = buffer.substring(boundary + 2); boundary = buffer.indexOf("\n\n");
                        try {
                            const eventData = JSON.parse(chunkDataString);
                            if (eventData.error) { this.updateMessageInDOM(tempAssistantMessageId, `Error: ${eventData.error}`); this.showAlert(eventData.error, 'danger'); return; }
                            if (eventData.chunk) { fullResponseText += eventData.chunk; this.updateMessageInDOM(tempAssistantMessageId, fullResponseText); }
                            if (eventData.done) { // Final event from server
                                // Replace temporary assistant message ID and data with final server-provided data
                                if (this.messageElements[tempAssistantMessageId] && eventData.message_id) {
                                    this.messageElements[tempAssistantMessageId].id = eventData.message_id;
                                    this.messageElements[eventData.message_id] = this.messageElements[tempAssistantMessageId];
                                    delete this.messageElements[tempAssistantMessageId];
                                }
                                if (this.messageTree[tempAssistantMessageId] && eventData.message_id) {
                                    this.messageTree[eventData.message_id] = this.messageTree[tempAssistantMessageId];
                                    this.messageTree[eventData.message_id].id = eventData.message_id;
                                    this.messageTree[eventData.message_id].content = fullResponseText; // Ensure full_response from server is used if different
                                    this.messageTree[eventData.message_id].model = eventData.model;
                                    this.messageTree[eventData.message_id].token_usage = eventData.token_usage;
                                    this.messageTree[eventData.message_id].parent_id = eventData.parent_id; // Ensure correct parent
                                    delete this.messageTree[tempAssistantMessageId];
                                } else if (eventData.message_id) { // If temp message wasn't in tree but we got a final ID
                                     this.messageTree[eventData.message_id] = { id: eventData.message_id, role: 'assistant', content: fullResponseText, parent_id: eventData.parent_id, children: [], model: eventData.model, timestamp: new Date().toISOString(), token_usage: eventData.token_usage };
                                }
                                this.updateMessageInDOM(eventData.message_id, fullResponseText, { model: eventData.model });

                                // Update user message ID if server corrected it (e.g., if it was first message)
                                if (this.messageElements[tempUserMessageId] && eventData.parent_id && tempUserMessageId !== eventData.parent_id) {
                                    this.messageElements[eventData.parent_id] = this.messageElements[tempUserMessageId];
                                    this.messageElements[eventData.parent_id].id = eventData.parent_id;
                                    delete this.messageElements[tempUserMessageId];
                                }
                                if (this.messageTree[tempUserMessageId] && eventData.parent_id && tempUserMessageId !== eventData.parent_id) {
                                    this.messageTree[eventData.parent_id] = this.messageTree[tempUserMessageId];
                                    this.messageTree[eventData.parent_id].id = eventData.parent_id;
                                    delete this.messageTree[tempUserMessageId];
                                }

                                if (eventData.conversation_id) this.currentConversationId = eventData.conversation_id;
                                this.updateAllSiblingIndicators(); // Update indicators as new children might have been added
                                return;
                            }
                        } catch (e) { console.warn("[WARN] Could not parse SSE event data:", chunkDataString, e); }
                    }
                }
            } else { // Non-streaming
                const response = await fetch(endpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: messageContent })
                });
                const data = await response.json(); this.showThinking(false);
                if (data.error) { this.showAlert(data.error, 'danger'); this.addMessageToDOM('system', `Error: ${data.error}`); }
                else {
                     // Update user message ID if server corrected it
                    if (this.messageElements[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                        const tempUserMsgEl = document.getElementById(tempUserMessageId);
                        if (tempUserMsgEl) { tempUserMsgEl.id = data.parent_id; }
                        this.messageElements[data.parent_id] = this.messageElements[tempUserMessageId];
                        delete this.messageElements[tempUserMessageId];
                    }
                    if (this.messageTree[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                        this.messageTree[data.parent_id] = this.messageTree[tempUserMessageId];
                        this.messageTree[data.parent_id].id = data.parent_id;
                        delete this.messageTree[tempUserMessageId];
                    } else if (data.parent_id && !this.messageTree[data.parent_id] && this.messageTree[tempUserMessageId]) {
                        // If user message ID changed and was not in tree under new ID, update it.
                        this.messageTree[data.parent_id] = this.messageTree[tempUserMessageId];
                        this.messageTree[data.parent_id].id = data.parent_id;
                        if(tempUserMessageId !== data.parent_id) delete this.messageTree[tempUserMessageId];
                    }

                    this.addMessageToDOM('assistant', data.response, data.message_id, { model: data.model, parent_id: data.parent_id, token_usage: data.token_usage });
                    if (data.conversation_id) this.currentConversationId = data.conversation_id;
                }
            }
        } catch (error) {
            console.error(`[ERROR] Failed to send message via ${endpoint}:`, error);
            this.showAlert('Failed to send message', 'danger');
            this.addMessageToDOM('system', `Error: connection issue or server error.`);
            this.showThinking(false);
        }
    }

    updateMessageInDOM(messageId, newContent, newMetadata = {}) {
        // This function updates an existing message in the DOM.
        const messageDiv = this.messageElements[messageId] || document.getElementById(messageId);
        if (!messageDiv) { console.warn(`[WARN] updateMessageInDOM: Message element ${messageId} not found.`); return; }

        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.innerHTML = this.formatMessageContent(newContent); // Re-parse and highlight
            this.applyCodeHighlighting(contentDiv);
        }

        if (newMetadata.model) {
            const modelBadge = messageDiv.querySelector('.message-header .badge.bg-secondary');
            if (modelBadge) modelBadge.textContent = newMetadata.model.split('/').pop(); // Show short model name
        }

        // Update messageTree as well
        if (this.messageTree[messageId]) {
            this.messageTree[messageId].content = newContent;
            if (newMetadata.model) this.messageTree[messageId].model = newMetadata.model;
            // Update other metadata if provided, e.g., token_usage
        }
        this.scrollToBottom();
    }

    getLastMessageIdFromActiveBranchDOM() {
        // Finds the ID of the last message element in the chat container.
        const chatMessagesContainer = document.getElementById('chatMessages');
        const messageElementsInDOM = chatMessagesContainer.querySelectorAll('.message-row');
        return messageElementsInDOM.length > 0 ? messageElementsInDOM[messageElementsInDOM.length - 1].id : null;
    }

    async handleCommand(command) {
        console.log(`[DEBUG] Handling command: ${command}`);
        if (command === '/help') { this.showHelp(); return; }
        try {
            const response = await fetch(`${this.apiBase}/api/command`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command })
            });
            const data = await response.json();
            if (data.error) { this.showAlert(data.error, 'danger'); }
            else if (data.message && !data.success) { this.addMessageToDOM('system', data.message); }

            if (data.success) { // Command was successful, might need UI updates
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
                const convNameEl = document.getElementById('conversationName');
                if (convNameEl && data.conversation_name) convNameEl.textContent = data.conversation_name;

                if (data.full_message_tree) { this.messageTree = data.full_message_tree; this._rebuildMessageTreeRelationships(); }

                if (data.history && Array.isArray(data.history)) { this.rebuildChatFromHistory(data.history); }
                else if (command.startsWith('/new')) { this.clearChatDisplay(); this.messageTree = {}; } // Clear for new if no history

                if (data.model) {
                    this.currentModelName = data.model; // Update internal tracking
                    this.updateModelDisplay(data.model);
                }
                if (data.system_instruction !== undefined) {
                    this.currentSystemInstruction = data.system_instruction;
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                }

                // Update sidebar form based on returned params and streaming status
                // This will correctly adjust the Max Tokens slider based on the potentially new model
                this.updateModelSettingsSidebarForm(
                    data.params || this.appSettings.params, // Fallback to appSettings if not in response
                    data.streaming !== undefined ? data.streaming : this.streamingEnabled,
                    this.currentSystemInstruction
                );

                if (data.streaming !== undefined) { // Update client's session streaming status
                    this.streamingEnabled = data.streaming;
                    this.updateStreamingStatusDisplay(this.streamingEnabled);
                }

                if (data.message && data.success) this.showAlert(data.message, 'info');

                // Reload conversations list for relevant commands
                if (command.startsWith('/new') || command.startsWith('/load') || command.startsWith('/list') || command.startsWith('/save') || command.startsWith('/delete') || command.startsWith('/rename') || command.startsWith('/duplicate')) {
                    await this.loadConversations();
                }
            }
        } catch (error) { console.error("[ERROR] Command failed:", error); this.showAlert('Command failed', 'danger'); }
    }

    displayConversationsList(conversations) {
        // This function populates the conversations list in the left sidebar.
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = ''; if (!Array.isArray(conversations)) return;
        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item conversation-list-item position-relative';
            const createdDate = conv.created_at ? new Date(conv.created_at).toLocaleDateString([], { year: '2-digit', month: 'numeric', day: 'numeric' }) : 'N/A';
            // Use conversation_id if available (more reliable for actions), fallback to filename.
            const convIdForActions = conv.conversation_id || conv.filename;
             // For loading, filename is often the primary identifier on the backend if ID isn't directly used.
            const convIdForLoading = conv.filename || conv.conversation_id || conv.title;


            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" href="#" onclick="app.loadConversationByName('${convIdForLoading.replace(/'/g, "\\'")}')">
                    <div style="max-width: calc(100% - 30px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        <strong id="conv-title-${convIdForActions}">${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count || 0} messages • ${createdDate}</small>
                    </div>
                </a>
                <div class="conversation-actions-menu position-absolute end-0 me-1" style="top: 50%; transform: translateY(-50%); z-index: 10;">
                     <button class="btn btn-sm btn-light py-0 px-1 three-dots-btn" aria-expanded="false" aria-controls="dropdown-${convIdForActions}" title="Conversation actions"><i class="bi bi-three-dots-vertical"></i></button>
                     <div class="dropdown-menu conversation-item-dropdown p-1" id="dropdown-${convIdForActions}" style="min-width: auto;">
                         <button class="dropdown-item d-flex align-items-center py-1 px-2" type="button" onclick="app.promptDuplicateConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-copy me-2"></i>Duplicate</button>
                         <button class="dropdown-item d-flex align-items-center py-1 px-2" type="button" onclick="app.promptRenameConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-pencil-square me-2"></i>Rename</button>
                         <div class="dropdown-divider my-1"></div>
                         <button class="dropdown-item d-flex align-items-center py-1 px-2 text-danger" type="button" onclick="app.confirmDeleteConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-trash me-2"></i>Delete</button>
                    </div>
                </div>`;
            listElement.appendChild(li);
        });
    }

    displayModelsList(models) {
        // This function populates the model selector modal table.
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = ''; if (!Array.isArray(models)) return;
        models.forEach(model => {
            const tr = document.createElement('tr');
            const outputLimit = this.modelCapabilities[model.name]?.output_token_limit || 'N/A';
            const inputLimit = this.modelCapabilities[model.name]?.input_token_limit || 'N/A';
            tr.innerHTML = `
                <td><code>${model.name}</code></td><td>${model.display_name}</td>
                <td>${inputLimit}</td><td>${outputLimit}</td>
                <td><button class="btn btn-sm btn-primary" onclick="app.selectModel('${model.name}')">Select</button></td>`;
            tbody.appendChild(tr);
        });
    }

    rebuildChatFromHistory(history) {
        // Rebuilds the entire chat display from a history array.
        console.log("[DEBUG] Rebuilding chat display from history array. Length:", history.length);
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = ''; // Clear existing messages
        this.messageElements = {}; // Clear DOM element cache

        const placeholderHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;

        if (!Array.isArray(history) || history.length === 0) {
            // If history is empty, check if messageTree also implies no messages.
            // The messageTree might have structure even if the active branch history is empty (e.g., a new conv).
            if (Object.keys(this.messageTree).length === 0 ||
                (this.messageTree.metadata && Object.keys(this.messageTree.messages || {}).length === 0)) {
                chatMessages.innerHTML = placeholderHTML;
            }
            this.updateAllSiblingIndicators(); // Still update indicators (might clear them)
            return;
        }

        history.forEach(msg => {
            this.addMessageToDOM(msg.role, msg.content, msg.id, {
                model: msg.model,
                timestamp: msg.timestamp,
                parent_id: msg.parent_id,
                token_usage: msg.token_usage,
                attachments: msg.attachments
            });
        });
        this.updateAllSiblingIndicators(); // Update all indicators after rebuilding
    }

    async retryMessage(messageId) {
        // Retries generating an AI response for a previous user message.
        console.log(`[DEBUG] Retrying assistant message: ${messageId}`); this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, { method: 'POST' });
            const data = await response.json();
            if (data.error) { this.showAlert(data.error, 'danger'); return; }

            // Update client state from response
            this.currentConversationId = data.conversation_id;
            const convNameEl = document.getElementById('conversationName');
            if (convNameEl && data.conversation_name) convNameEl.textContent = data.conversation_name;

            if (data.system_instruction !== undefined) {
                 this.currentSystemInstruction = data.system_instruction;
                 this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                 // Params and streaming preference might also be in `data` if backend sends full status
                 this.updateModelSettingsSidebarForm(
                    data.params || this.appSettings.params,
                    data.streaming !== undefined ? data.streaming : this.streamingEnabled,
                    this.currentSystemInstruction
                 );
            }

            if (data.full_message_tree) { this.messageTree = data.full_message_tree; this._rebuildMessageTreeRelationships(); }
            if (data.history && Array.isArray(data.history)) { this.rebuildChatFromHistory(data.history); }

            this.showAlert('Generated new response', 'success');
        } catch (error) { console.error("[ERROR] Failed to retry message:", error); this.showAlert('Failed to retry message', 'danger'); }
        finally { this.showThinking(false); }
    }

    async navigateSibling(messageId, direction) {
        // Navigates to a sibling (alternative) AI response.
        console.log(`[DEBUG] Navigating (direction: ${direction}) from message: ${messageId}`); this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/navigate`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, direction })
            });
            const data = await response.json();
            if (data.error) { this.showAlert(data.error, 'danger'); return; }

            // Update client state from response
            this.currentConversationId = data.conversation_id;
            const convNameEl = document.getElementById('conversationName');
            if (convNameEl && data.conversation_name) convNameEl.textContent = data.conversation_name;

            if (data.system_instruction !== undefined) {
                 this.currentSystemInstruction = data.system_instruction;
                 this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                 this.updateModelSettingsSidebarForm(
                    data.params || this.appSettings.params,
                    data.streaming !== undefined ? data.streaming : this.streamingEnabled,
                    this.currentSystemInstruction
                 );
            }

            if (data.full_message_tree) { this.messageTree = data.full_message_tree; this._rebuildMessageTreeRelationships(); }
            if (data.history && Array.isArray(data.history)) { this.rebuildChatFromHistory(data.history); }
            else { this.clearChatDisplay(); this.showAlert('Navigation resulted in empty history.', 'warning'); }

            if (direction !== 'none' && data.total_siblings > 1) this.showAlert(`Switched to response ${data.sibling_index + 1} of ${data.total_siblings}`, 'info');

        } catch (error) { console.error("[ERROR] Failed to navigate sibling:", error); this.showAlert('Failed to navigate to sibling', 'danger'); }
        finally { this.showThinking(false); }
    }

    updateSiblingIndicators(parentId) {
        // Updates the "(1 / 3)" style indicators for sibling messages.
        if (!parentId || !this.messageTree[parentId] || !Array.isArray(this.messageTree[parentId].children)) return;

        const siblings = this.messageTree[parentId].children;
        siblings.forEach((siblingId, index) => {
            const element = this.messageElements[siblingId] || document.getElementById(siblingId);
            if (element) {
                let indicatorSpan = element.querySelector('.branch-indicator');
                let indicatorTextEl = element.querySelector('.branch-indicator-text'); // Ensure this sub-element is selected

                // Create indicator if it doesn't exist
                if (!indicatorSpan) {
                    const header = element.querySelector('.message-header');
                    if (header) {
                        indicatorSpan = document.createElement('span'); indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                        indicatorTextEl = document.createElement('span'); indicatorTextEl.className = 'branch-indicator-text';
                        indicatorSpan.appendChild(indicatorTextEl);

                        const modelBadge = header.querySelector('.badge.bg-secondary');
                        if (modelBadge) modelBadge.insertAdjacentElement('afterend', indicatorSpan);
                        else header.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan); // Fallback if no model badge
                    }
                }

                if (indicatorSpan && indicatorTextEl) { // Check both exist
                    if (siblings.length > 1) {
                        indicatorTextEl.textContent = `${index + 1} / ${siblings.length}`;
                        indicatorSpan.style.display = 'inline-block';
                    } else {
                        indicatorSpan.style.display = 'none';
                    }
                }

                // Update navigation buttons state
                const prevBtn = element.querySelector('.btn-prev-sibling'); const nextBtn = element.querySelector('.btn-next-sibling');
                if (prevBtn && nextBtn) {
                    const showNav = siblings.length > 1;
                    prevBtn.style.display = showNav ? 'inline-flex' : 'none';
                    nextBtn.style.display = showNav ? 'inline-flex' : 'none';
                    prevBtn.disabled = (index === 0);
                    nextBtn.disabled = (index === siblings.length - 1);
                }
            }
        });
    }

    updateAllSiblingIndicators() {
        // Iterates through the message tree to update all sibling indicators.
        const displayedParentIds = new Set();
        // Collect all parent IDs that have children currently in the DOM or messageTree
        Object.values(this.messageElements).forEach(domEl => {
            const msgNode = this.messageTree[domEl.id];
            if (msgNode && msgNode.parent_id && this.messageTree[msgNode.parent_id]) {
                displayedParentIds.add(msgNode.parent_id);
            }
        });
        // Also consider parents from the messageTree directly, as DOM might not be fully synced yet
        for (const msgId in this.messageTree) {
            const msgNode = this.messageTree[msgId];
            if (msgNode.children && msgNode.children.length > 0) {
                displayedParentIds.add(msgId);
            }
        }
        displayedParentIds.forEach(pid => this.updateSiblingIndicators(pid));
    }

    addMessageToDOM(role, content, messageId, metadata = {}) {
        const uniqueMessageId = messageId || `msg-${role}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const contentString = (typeof content === 'string') ? content : JSON.stringify(content);

        // Update or create in messageTree
        if (!this.messageTree[uniqueMessageId]) {
            this.messageTree[uniqueMessageId] = {
                id: uniqueMessageId, role, content: contentString, parent_id: metadata.parent_id || null, children: [],
                model: metadata.model, timestamp: metadata.timestamp || new Date().toISOString(),
                token_usage: metadata.token_usage || {}, attachments: metadata.attachments
            };
        } else { // If message already in tree (e.g. temp message being finalized)
            this.messageTree[uniqueMessageId].content = contentString; // Update content
            if (metadata.model) this.messageTree[uniqueMessageId].model = metadata.model;
            if (metadata.token_usage) this.messageTree[uniqueMessageId].token_usage = metadata.token_usage;
            if (metadata.attachments) this.messageTree[uniqueMessageId].attachments = metadata.attachments;
            // Parent and children relationships should be handled carefully if ID changes or is finalized
        }

        // Ensure parent-child relationship in messageTree is updated
        if (metadata.parent_id && this.messageTree[metadata.parent_id]) {
            const parentNodeInTree = this.messageTree[metadata.parent_id];
            if (!Array.isArray(parentNodeInTree.children)) parentNodeInTree.children = [];
            if (!parentNodeInTree.children.includes(uniqueMessageId)) {
                parentNodeInTree.children.push(uniqueMessageId);
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const emptyState = chatMessages.querySelector('.text-center.text-muted.py-5');
        if (emptyState) emptyState.remove(); // Remove placeholder if it exists

        let messageRow = this.messageElements[uniqueMessageId]; // Check if DOM element already exists
        if (!messageRow) {
            messageRow = document.createElement('div');
            messageRow.className = `message-row message-${role}`;
            messageRow.id = uniqueMessageId;
            chatMessages.appendChild(messageRow);
            this.messageElements[uniqueMessageId] = messageRow; // Cache the DOM element
        }

        let iconClass, roleLabel;
        switch (role) {
            case 'user': iconClass = 'bi-person-circle'; roleLabel = 'You'; break;
            case 'assistant': iconClass = 'bi-robot'; roleLabel = 'CannonAI'; break;
            default: iconClass = 'bi-info-circle'; roleLabel = 'System'; break;
        }
        const messageTimestamp = this.messageTree[uniqueMessageId]?.timestamp || new Date().toISOString();
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        let headerHTML = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && this.messageTree[uniqueMessageId]?.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${this.messageTree[uniqueMessageId].model.split('/').pop()}</span>`;
        }
        // Sibling indicator will be added by updateSiblingIndicators
        headerHTML += ` <span class="text-muted ms-auto message-timestamp-display">${displayTime}</span>`;

        let actionsHTML = '';
        if (role === 'assistant') {
            actionsHTML = `
                <div class="message-actions">
                    <button class="btn btn-sm btn-retry" onclick="app.retryMessage('${uniqueMessageId}')" title="Generate another response"><i class="bi bi-arrow-clockwise"></i></button>
                    <button class="btn btn-sm btn-prev-sibling" onclick="app.navigateSibling('${uniqueMessageId}', 'prev')" title="Previous response" style="display: none;"><i class="bi bi-chevron-left"></i></button>
                    <button class="btn btn-sm btn-next-sibling" onclick="app.navigateSibling('${uniqueMessageId}', 'next')" title="Next response" style="display: none;"><i class="bi bi-chevron-right"></i></button>
                </div>`;
        }
        messageRow.innerHTML = `
            <div class="message-icon me-2 ms-2"><i class="bi ${iconClass} fs-4"></i></div>
            <div class="message-body">
                <div class="message-header d-flex align-items-center mb-1">${headerHTML}</div>
                <div class="message-content p-2 rounded shadow-sm">${this.formatMessageContent(contentString)}</div>
                ${actionsHTML}
            </div>`;

        // Add placeholder for sibling indicator if it's an assistant message
        if (role === 'assistant') {
            const headerElement = messageRow.querySelector('.message-header');
            if (headerElement) {
                const indicatorSpan = document.createElement('span');
                indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                indicatorSpan.style.display = 'none'; // Initially hidden
                const indicatorText = document.createElement('span');
                indicatorText.className = 'branch-indicator-text';
                indicatorSpan.appendChild(indicatorText);

                const modelBadge = headerElement.querySelector('.badge.bg-secondary');
                if (modelBadge) modelBadge.insertAdjacentElement('afterend', indicatorSpan);
                else headerElement.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan);
            }
        }

        this.applyCodeHighlighting(messageRow);
        this.reRenderAllMessagesVisuals(); // Apply app settings like avatar/timestamp visibility
        this.scrollToBottom();

        // Update sibling indicators for the parent of this new message
        if (metadata.parent_id) {
            this.updateSiblingIndicators(metadata.parent_id);
        }
        // If this new message is a user message and it might have children (e.g., loading history)
        // update indicators for its own children as well.
        if (role === 'user' && this.messageTree[uniqueMessageId] && this.messageTree[uniqueMessageId].children.length > 0) {
            this.updateSiblingIndicators(uniqueMessageId);
        }
    }

    formatMessageContent(content) {
        // Parses markdown and prepares content for display.
        if (typeof content !== 'string') { content = String(content); }
        try { return marked.parse(content); } catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error, "Content was:", content);
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/\n/g, '<br>'); // Basic newline to <br> for unparseable content
        }
    }

    applyCodeHighlighting(containerElement) {
        // Applies syntax highlighting to code blocks within the given container.
        containerElement.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
            // Apply line numbers based on app settings
            if (this.appSettings.showLineNumbers) {
                if (!block.classList.contains('line-numbers-active')) { // Avoid re-adding
                    const lines = block.innerHTML.split('\n');
                    // Handle potential trailing newline from highlight.js
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') ? lines.slice(0, -1) : lines;
                    block.innerHTML = effectiveLines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                    block.classList.add('line-numbers-active');
                }
            } else { // Remove line numbers if setting is off
                if (block.classList.contains('line-numbers-active')) {
                    block.innerHTML = block.innerHTML.replace(/<span class="line-number">.*?<\/span>/g, '');
                    block.classList.remove('line-numbers-active');
                }
            }
        });
    }

    clearChatDisplay() {
        // Clears the chat message area and resets message cache.
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
        this.messageElements = {}; // Clear the DOM element cache
    }

    scrollToBottom() {
        // Scrolls the chat message area to the bottom.
        const chatContainer = document.getElementById('chatMessages'); // Changed from chatContainer to chatMessages
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    showThinking(show) {
        // Shows or hides the "CannonAI is thinking..." indicator.
        document.getElementById('thinkingIndicator').classList.toggle('d-none', !show);
    }

    updateConnectionStatus(connected = true) {
        // Updates the connection status display in the status bar.
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl) statusEl.innerHTML = `<i class="bi bi-circle-fill ${connected ? 'text-success pulsate-connection' : 'text-danger'}"></i> ${connected ? 'Connected' : 'Disconnected'}`;
    }

    updateModelDisplay(modelName) {
        // Updates the current model display in the header.
        const modelEl = document.getElementById('currentModelDisplay'); // Ensure this ID matches HTML
        if (modelEl) modelEl.textContent = modelName ? modelName.split('/').pop() : 'N/A'; // Show short name
    }

    updateStreamingStatusDisplay(enabled) {
        // Updates the streaming status display in the status bar (reflects client's session default).
        const streamingModeEl = document.getElementById('streamingMode');
        if (streamingModeEl) streamingModeEl.textContent = enabled ? 'ON' : 'OFF';
    }

    updateSystemInstructionStatusDisplay(instruction) {
        // Updates the system instruction preview in the status bar.
        const displayEl = document.getElementById('systemInstructionDisplay');
        if (displayEl) {
            const shortInstruction = instruction && instruction.length > 20 ? instruction.substring(0, 20) + "..." : (instruction || "Default");
            displayEl.textContent = shortInstruction;
            const parentStatusEl = document.getElementById('systemInstructionStatus');
            if(parentStatusEl) parentStatusEl.title = instruction || "Default System Instruction";
        }
    }

    updateModelSettingsSidebarForm(params, streamingStatus, systemInstruction) {
        // Populates the right sidebar form with current settings.
        // `params` are the generation parameters (temp, top_p, top_k, max_output_tokens)
        // `streamingStatus` is the current streaming preference for the session/conversation
        // `systemInstruction` is the current conversation's system instruction (used for modal, not directly here)

        if (!params) params = {}; // Ensure params is an object

        // Temperature
        const tempSlider = document.getElementById('temperatureInput');
        const tempDisplay = document.getElementById('temperatureValueDisplay');
        if (tempSlider && tempDisplay) {
            const tempValue = parseFloat(params.temperature !== undefined ? params.temperature : 0.7);
            tempSlider.value = tempValue;
            tempDisplay.textContent = tempValue.toFixed(2);
        }

        // Max Output Tokens (Slider & Input)
        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');
        const maxTokensValueDisplay = document.getElementById('maxTokensValueDisplay');

        if (maxTokensSlider && maxTokensInput && maxTokensValueDisplay) {
            const currentModelMax = this.modelCapabilities[this.currentModelName]?.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS;

            maxTokensSlider.min = this.MIN_OUTPUT_TOKENS;
            maxTokensInput.min = this.MIN_OUTPUT_TOKENS;
            maxTokensSlider.max = currentModelMax;
            maxTokensInput.max = currentModelMax; // Also set max for the number input
            maxTokensSlider.step = this.TOKEN_SLIDER_STEP;
            maxTokensInput.step = this.TOKEN_SLIDER_STEP;

            let currentSetValue = parseInt(params.max_output_tokens !== undefined ? params.max_output_tokens : 800);
            // Clamp the current value to be within the model's new limits
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax;
            if (currentSetValue < this.MIN_OUTPUT_TOKENS) currentSetValue = this.MIN_OUTPUT_TOKENS;

            // Align to step
            currentSetValue = Math.round((currentSetValue - this.MIN_OUTPUT_TOKENS) / this.TOKEN_SLIDER_STEP) * this.TOKEN_SLIDER_STEP + this.MIN_OUTPUT_TOKENS;
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax; // Re-clamp after step alignment


            maxTokensSlider.value = currentSetValue;
            maxTokensInput.value = currentSetValue;
            maxTokensValueDisplay.textContent = currentSetValue;
        }

        // Top-P
        const topPSlider = document.getElementById('topPInput');
        const topPDisplay = document.getElementById('topPValueDisplay');
        if (topPSlider && topPDisplay) {
            const topPValue = parseFloat(params.top_p !== undefined ? params.top_p : 0.95);
            topPSlider.value = topPValue;
            topPDisplay.textContent = topPValue.toFixed(2);
        }

        // Top-K
        const topKInput = document.getElementById('topKInput');
        if (topKInput) topKInput.value = parseInt(params.top_k !== undefined ? params.top_k : 40);

        // Streaming Toggle (in sidebar, reflects session/conversation preference)
        const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggleSidebar) streamingToggleSidebar.checked = streamingStatus;
    }

    showNewConversationModal() {
        const titleInput = document.getElementById('conversationTitleInput');
        if (titleInput) titleInput.value = ''; // Clear previous title
        else console.error("Element 'conversationTitleInput' not found.");
        this.modals.newConversation.show();
    }

    async createNewConversation() {
        const titleInput = document.getElementById('conversationTitleInput');
        const title = titleInput ? titleInput.value.trim() : '';
        try {
            await this.handleCommand(`/new ${title}`); // Server handles actual creation and state update
            this.modals.newConversation.hide();
        } catch (error) { this.showAlert('Failed to create new conversation', 'danger'); }
    }

    async loadConversationByName(conversationNameOrFilename) {
        await this.handleCommand(`/load ${conversationNameOrFilename}`); // Server handles loading and state update
    }

    async saveConversation() { await this.handleCommand('/save'); }

    showModelSelector() {
        // `loadModels()` is now called in `loadInitialData`. If models list needs refresh, call it here.
        // await this.loadModels(); // Optionally refresh if models can change dynamically without app restart
        this.modals.modelSelector.show();
    }

    async selectModel(modelName) {
        // This will trigger a call to `/api/command` with `/model modelName`
        // The backend (APIHandlers) will update the client's model.
        // Then, `this.loadStatus()` (called eventually or directly) will refresh the UI,
        // including the `currentModelDisplay` and the Max Tokens slider via `updateModelSettingsSidebarForm`.
        await this.handleCommand(`/model ${modelName}`);
        const modelSelectorModalEl = document.getElementById('modelSelectorModal');
        if (modelSelectorModalEl && modelSelectorModalEl.classList.contains('show')) {
            this.modals.modelSelector.hide();
        }
    }

    toggleModelSettingsSidebar() {
        const sidebar = document.getElementById('modelSettingsSidebar');
        const mainContent = document.getElementById('mainContent');
        if (!sidebar || !mainContent) return;

        const isOpen = !sidebar.classList.contains('d-none'); // Check current state BEFORE toggling
        sidebar.classList.toggle('d-none');
        this.rightSidebarOpen = !isOpen; // Update state AFTER toggling

        if (this.rightSidebarOpen) {
            mainContent.classList.remove(...this.mainContentDefaultClasses);
            mainContent.classList.add(...this.mainContentRightSidebarOpenClasses);
        } else {
            mainContent.classList.remove(...this.mainContentRightSidebarOpenClasses);
            mainContent.classList.add(...this.mainContentDefaultClasses);
        }
    }

    async saveModelSettingsFromSidebar() {
        // System instruction is handled by its own modal and API endpoint.
        // This function saves generation parameters and session streaming preference.
        const params = {
            temperature: parseFloat(document.getElementById('temperatureInput').value),
            // Use the number input for max_output_tokens as it might have a more precise value
            max_output_tokens: parseInt(document.getElementById('maxTokensInput').value),
            top_p: parseFloat(document.getElementById('topPInput').value),
            top_k: parseInt(document.getElementById('topKInput').value)
        };
        const streaming = document.getElementById('streamingToggleRightSidebar').checked; // This is the client's desired streaming for session

        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params, streaming }) // Send only params and session streaming
            });
            const data = await response.json();
            if (data.success) {
                this.streamingEnabled = data.streaming; // Update client's session streaming status
                this.updateStreamingStatusDisplay(this.streamingEnabled);

                // Re-populate sidebar form with confirmed settings from server
                // This is important if server adjusted any values (e.g., clamping)
                // The currentSystemInstruction is for the active conversation, not changed here.
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction);

                this.showAlert('Session settings (params, streaming) applied', 'success');
            } else { this.showAlert(data.error || 'Failed to apply session settings', 'danger'); }
        } catch (error) { this.showAlert('Failed to apply session settings', 'danger'); }
    }

    showSystemInstructionModal() {
        const modalInput = document.getElementById('systemInstructionModalInput');
        if (modalInput) {
            modalInput.value = this.currentSystemInstruction; // Populate with current conversation's instruction
        }
        if (this.modals.systemInstruction) {
            this.modals.systemInstruction.show();
        } else {
            this.showAlert("System instruction modal not available.", "warning");
        }
    }

    async saveSystemInstructionFromModal() {
        const newInstructionInput = document.getElementById('systemInstructionModalInput');
        if (!newInstructionInput) { this.showAlert("Cannot find system instruction input.", "danger"); return; }
        const newInstruction = newInstructionInput.value;

        if (!this.currentConversationId) {
            this.showAlert("No active conversation to save system instruction to. Will apply to next new conversation if default is not overridden by loaded conversation.", "warning");
            this.currentSystemInstruction = newInstruction; // Update client's default for next new conv
            this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
            if (this.modals.systemInstruction) this.modals.systemInstruction.hide();
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/api/conversation/${this.currentConversationId}/system_instruction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ system_instruction: newInstruction })
            });
            const data = await response.json();
            if (data.success) {
                this.currentSystemInstruction = data.system_instruction; // Update client's working copy for active conv
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);

                // Update the conversation_data in the client's messageTree for the active conversation
                if (this.currentConversationId && this.messageTree && this.messageTree.metadata) {
                     // If metadata is at the root of the messageTree (less likely for full_message_tree from server)
                    this.messageTree.metadata.system_instruction = data.system_instruction;
                } else if (this.currentConversationId && this.messageTree[this.currentConversationId] && this.messageTree[this.currentConversationId].metadata) {
                    // If messageTree is a map of conversation_id -> conversation_data
                    this.messageTree[this.currentConversationId].metadata.system_instruction = data.system_instruction;
                } else if (this.currentConversationId && this.messageTree.messages && this.messageTree.metadata) {
                     // If full_message_tree is the structure {metadata: {}, messages: {}, branches: {}} for the current conv
                    this.messageTree.metadata.system_instruction = data.system_instruction;
                }


                this.showAlert('System instruction saved for current conversation.', 'success');
                if (this.modals.systemInstruction) this.modals.systemInstruction.hide();
            } else {
                this.showAlert(data.error || 'Failed to save system instruction.', 'danger');
            }
        } catch (error) {
            console.error("Error saving system instruction:", error);
            this.showAlert('Error saving system instruction.', 'danger');
        }
    }

    async toggleStreaming() { await this.handleCommand('/stream'); } // Toggles client session default, reloads status

    showHistory() { this.showAlert('Full conversation history for the active branch is displayed.', 'info'); }

    showHelp() {
        const helpContent = `<h5>Available Commands (type in chat):</h5><ul>
            <li><code>/new [title]</code> - Start a new conversation.</li>
            <li><code>/load [name/id]</code> - Load a conversation.</li>
            <li><code>/save</code> - Save current conversation.</li>
            <li><code>/list</code> - Refresh and show saved conversations.</li>
            <li><code>/model [name]</code> - Change AI model (for current provider). Lists if no name.</li>
            <li><code>/stream</code> - Toggle client's session streaming preference.</li>
            <li><code>/help</code> - Show this help.</li></ul>
            <p><small>Generation parameters and system instructions are managed via UI elements in the header and right sidebar.</small></p>`;
        this.addMessageToDOM('system', helpContent, `help-${Date.now()}`);
    }

    // App Settings (Theme, Font, etc. - LocalStorage)
    loadAppSettings() {
        const defaults = {
            theme: 'light', fontSize: 16, fontFamily: 'system-ui',
            showTimestamps: true, showAvatars: true, enableAnimations: true,
            compactMode: false, codeTheme: 'github-dark', showLineNumbers: true,
            defaultSystemInstruction: "You are a helpful assistant.", // For new conversations
            params: { temperature: 0.7, max_output_tokens: 800, top_p: 0.95, top_k: 40 } // Default generation params
        };
        try {
            const saved = localStorage.getItem('cannonAIAppSettings');
            // Merge saved settings with defaults, ensuring all keys from defaults are present
            const loaded = saved ? JSON.parse(saved) : {};
            return { ...defaults, ...loaded, params: { ...defaults.params, ...(loaded.params || {}) } };
        } catch (e) { return defaults; }
    }
    saveAppSettingsToStorage() { try { localStorage.setItem('cannonAIAppSettings', JSON.stringify(this.appSettings)); return true; } catch (e) { console.error("Error saving app settings:", e); return false; } }
    applyAppSettings() {
        this.applyTheme(this.appSettings.theme);
        document.documentElement.style.setProperty('--chat-font-size', `${this.appSettings.fontSize}px`);
        document.documentElement.style.setProperty('--chat-font-family', this.appSettings.fontFamily);
        document.body.classList.toggle('hide-timestamps', !this.appSettings.showTimestamps);
        document.body.classList.toggle('hide-avatars', !this.appSettings.showAvatars);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        this.updateCodeThemeLink(this.appSettings.codeTheme); // Applies code theme and re-highlights
        this.reRenderAllMessagesVisuals(); // Applies settings to existing messages
    }
    applyTheme(themeName) {
        document.body.classList.remove('theme-light', 'theme-dark');
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        document.body.classList.add(`theme-${effectiveTheme}`);

        let codeThemeToApply = this.appSettings.codeTheme;
        if (this.appSettings.codeTheme === 'default') { // 'default' means match UI theme
            codeThemeToApply = effectiveTheme === 'dark' ? 'github-dark' : 'github';
        }
        this.updateCodeThemeLink(codeThemeToApply, false); // Update link without re-saving 'default'
    }
    updateCodeThemeLink(themeName, saveSetting = true) {
        let link = document.querySelector('link[id="highlightjs-theme"]');
        if (!link) {
            link = document.createElement('link');
            link.id = 'highlightjs-theme';
            link.rel = 'stylesheet';
            document.head.appendChild(link);
        }
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeName}.min.css`;
        if (saveSetting) this.appSettings.codeTheme = themeName; // Save the actual theme applied if not 'default'
        // Re-highlight all code blocks after theme change
        document.querySelectorAll('pre code').forEach(block => {
            // If line numbers were active, they need to be stripped and re-applied or handled by a more robust highlighting update
            const parentPre = block.closest('pre');
            if (parentPre) {
                 const tempContent = block.textContent; // Get raw code
                 block.className = `language-${block.className.match(/language-(\S+)/)?.[1] || 'plaintext'} hljs`; // Reset classes
                 block.innerHTML = tempContent; // Put raw code back
                 hljs.highlightElement(block); // Re-apply highlight.js
                 this.applyCodeHighlighting(parentPre); // Re-apply line numbers if needed
            }
        });
    }
    showAppSettingsModal() {
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
        this.updatePreview(); this.modals.appSettings.show();
    }
    saveAppSettings() {
        this.appSettings = {
            theme: document.querySelector('input[name="theme"]:checked').value,
            fontSize: parseInt(document.getElementById('fontSize').value),
            fontFamily: document.getElementById('fontFamily').value,
            showTimestamps: document.getElementById('showTimestamps').checked,
            showAvatars: document.getElementById('showAvatars').checked,
            enableAnimations: document.getElementById('enableAnimations').checked,
            compactMode: document.getElementById('compactMode').checked,
            codeTheme: document.getElementById('codeTheme').value, // This will be the selected value e.g. "github-dark" or "default"
            showLineNumbers: document.getElementById('showLineNumbers').checked,
            // Preserve other settings like defaultSystemInstruction and params if they are part of appSettings
            defaultSystemInstruction: this.appSettings.defaultSystemInstruction,
            params: this.appSettings.params
        };
        if (this.saveAppSettingsToStorage()) {
            this.applyAppSettings();
            this.showAlert('App settings saved', 'success');
            this.modals.appSettings.hide();
        }
        else { this.showAlert('Failed to save app settings', 'danger'); }
    }
    resetAppSettings() {
        if (confirm('Reset all app settings to defaults? This will clear your locally stored preferences.')) {
            localStorage.removeItem('cannonAIAppSettings');
            this.appSettings = this.loadAppSettings(); // Load defaults
            this.applyAppSettings();
            this.showAppSettingsModal(); // Re-populate modal with defaults
            this.showAlert('App settings reset to defaults', 'info');
        }
    }
    updatePreview() {
        const preview = document.getElementById('settingsPreview'); if (!preview) return;
        preview.style.fontSize = `${document.getElementById('fontSize').value}px`;
        preview.style.fontFamily = document.getElementById('fontFamily').value;

        const previewAvatarContainer = preview.querySelector('#previewAvatarContainer');
        if(previewAvatarContainer) previewAvatarContainer.style.display = document.getElementById('showAvatars').checked ? 'flex' : 'none';

        const previewTimestamp = preview.querySelector('#previewTimestamp');
        if(previewTimestamp) previewTimestamp.style.display = document.getElementById('showTimestamps').checked ? 'inline' : 'none';

        const selectedThemeRadio = document.querySelector('input[name="theme"]:checked').value;
        let previewThemeClass = `theme-${selectedThemeRadio}`;
        if (selectedThemeRadio === 'auto') {
            previewThemeClass = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'theme-dark' : 'theme-light';
        }
        preview.className = `preview-area border rounded p-3 ${previewThemeClass}`;

        // Code theme preview in the modal requires applying the selected highlight.js theme to the preview code block
        const codeBlock = preview.querySelector('pre code');
        if (codeBlock) {
            let selectedCodeTheme = document.getElementById('codeTheme').value;
            if (selectedCodeTheme === 'default') {
                selectedCodeTheme = (previewThemeClass === 'theme-dark') ? 'github-dark' : 'github';
            }
            // This is tricky: highlight.js themes are loaded globally.
            // For preview, we might need a more isolated way or just trust the global theme change.
            // For simplicity, we'll assume the global theme change reflects well enough, or that `applyAppSettings` handles it.
            // Or, we can try to manually re-highlight with a temporary link (complex).
            // The most straightforward is that `updateCodeThemeLink` followed by `reRenderAllMessagesVisuals` (called by `applyAppSettings`)
            // should correctly style all code blocks, including this preview one if it's part of the main document flow.
            // Since the preview is IN the modal, it might need a specific re-highlight.
             hljs.highlightElement(codeBlock); // Re-highlight with current global theme.
             // Then apply line numbers based on the checkbox in the settings modal
            const showPreviewLineNumbers = document.getElementById('showLineNumbers').checked;
            if (showPreviewLineNumbers) {
                if (!codeBlock.classList.contains('line-numbers-active-preview')) {
                    const lines = codeBlock.innerHTML.split('\n');
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') ? lines.slice(0, -1) : lines;
                    codeBlock.innerHTML = effectiveLines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                    codeBlock.classList.add('line-numbers-active-preview');
                }
            } else {
                if (codeBlock.classList.contains('line-numbers-active-preview')) {
                    codeBlock.innerHTML = codeBlock.innerHTML.replace(/<span class="line-number">.*?<\/span>/g, '');
                    codeBlock.classList.remove('line-numbers-active-preview');
                }
            }
        }
    }
    reRenderAllMessagesVisuals() {
        // Applies visual settings (avatars, timestamps, compact mode, line numbers) to all messages.
        document.querySelectorAll('.message-row').forEach(messageEl => {
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) avatarEl.style.display = this.appSettings.showAvatars ? 'flex' : 'none';

            const timestampEl = messageEl.querySelector('.message-timestamp-display');
            if (timestampEl) timestampEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';

            this.applyCodeHighlighting(messageEl); // Re-applies line numbers based on current setting
        });
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations); // Animations are enabled by default
    }
    showAlert(message, type = 'info') {
        // Displays a dismissible alert at the bottom-right of the screen.
        const alertContainer = document.getElementById('alertContainer');
        if (!alertContainer) return;
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show m-0 mb-2`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        alertContainer.appendChild(alertDiv);
        const bsAlert = new bootstrap.Alert(alertDiv); // Initialize Bootstrap alert
        setTimeout(() => {
            if (bootstrap.Alert.getInstance(alertDiv)) bsAlert.close(); // Safely close
            else if (alertDiv.parentElement) alertDiv.remove(); // Fallback remove if instance is gone
        }, 5000); // Auto-dismiss after 5 seconds
    }

    // Conversation Action Handlers (Duplicate, Rename, Delete)
    async promptDuplicateConversation(conversationId, currentTitle) {
        // Use a Bootstrap modal for this in a real app, prompt is placeholder
        const newTitle = prompt(`Enter a title for the duplicated conversation (current: "${currentTitle}"):`, `Copy of ${currentTitle}`);
        if (newTitle && newTitle.trim() !== '') {
            await this.apiDuplicateConversation(conversationId, newTitle.trim());
        }
    }
    async apiDuplicateConversation(conversationId, newTitle) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/duplicate/${conversationId}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            if (data.success) { this.showAlert(`Conversation duplicated as "${data.new_title}"`, 'success'); await this.loadConversations(); }
            else { this.showAlert(data.error || 'Failed to duplicate conversation', 'danger'); }
        } catch (error) { console.error("[ERROR] Failed to duplicate:", error); this.showAlert('Client error duplicating conversation', 'danger'); }
        finally { this.showThinking(false); }
    }
    async promptRenameConversation(conversationId, currentTitle) {
        const newTitle = prompt(`Enter the new title for "${currentTitle}":`, currentTitle);
        if (newTitle !== null && newTitle.trim() !== '' && newTitle.trim() !== currentTitle) {
            await this.apiRenameConversation(conversationId, newTitle.trim());
        }
    }
    async apiRenameConversation(conversationId, newTitle) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/rename/${conversationId}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            if (data.success) {
                this.showAlert(`Conversation renamed to "${data.new_title}"`, 'success');
                await this.loadConversations(); // Refresh list
                // If current conversation was renamed, update its display name and tree
                if (this.currentConversationId === data.conversation_id) { // Use ID from response for matching
                    const convNameEl = document.getElementById('conversationName');
                    if(convNameEl) convNameEl.textContent = data.new_title;
                    // Update title in messageTree if it's the active one
                    if (this.messageTree && this.messageTree.metadata && this.currentConversationId === this.messageTree.metadata.conversation_id) {
                        this.messageTree.metadata.title = data.new_title;
                    } else if (this.currentConversationId && this.messageTree[this.currentConversationId] && this.messageTree[this.currentConversationId].metadata) {
                         this.messageTree[this.currentConversationId].metadata.title = data.new_title;
                    }
                }
            } else { this.showAlert(data.error || 'Failed to rename conversation', 'danger'); }
        } catch (error) { console.error("[ERROR] Failed to rename:", error); this.showAlert('Client error renaming conversation', 'danger'); }
        finally { this.showThinking(false); }
    }
    async confirmDeleteConversation(conversationId, title) {
        // Replace with a Bootstrap modal for confirmation
        if (confirm(`Are you sure you want to delete the conversation "${title}"? This cannot be undone.`)) {
            await this.apiDeleteConversation(conversationId);
        }
    }
    async apiDeleteConversation(conversationId) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/delete/${conversationId}`, { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showAlert(`Conversation deleted`, 'success');
                await this.loadConversations(); // Refresh list
                // If the deleted conversation was the active one, clear the UI and state
                if (this.currentConversationId === data.deleted_conversation_id) { // Use ID from response
                    this.currentConversationId = null;
                    this.clearChatDisplay();
                    this.messageTree = {}; // Clear message tree
                    const convNameEl = document.getElementById('conversationName');
                    if(convNameEl) convNameEl.textContent = 'New Conversation';
                    this.currentSystemInstruction = this.appSettings.defaultSystemInstruction || "You are a helpful assistant.";
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                    // Reset sidebar to defaults or based on a new "default" conversation state
                    this.updateModelSettingsSidebarForm(
                        this.appSettings.params || {},
                        this.streamingEnabled, // Keep session streaming preference
                        this.currentSystemInstruction
                    );
                }
            } else { this.showAlert(data.error || 'Failed to delete conversation', 'danger'); }
        } catch (error) { console.error("[ERROR] Failed to delete:", error); this.showAlert('Client error deleting conversation', 'danger'); }
        finally { this.showThinking(false); }
    }
}

const app = new CannonAIApp();
