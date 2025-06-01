/**
 * CannonAI GUI - Frontend JavaScript
 * Handles all UI interactions and communication with the Flask backend
 */

class CannonAIApp {
    constructor() {
        console.log("[DEBUG] Initializing CannonAIApp");

        this.apiBase = window.location.origin;
        this.currentConversationId = null;
        this.streamingEnabled = false; // Server's master streaming setting
        this.currentSystemInstruction = "You are a helpful assistant."; // Default

        this.modals = {};
        this.appSettings = this.loadAppSettings();
        this.messageTree = {}; // Stores the full message tree for the current conversation
        this.messageElements = {}; // Maps message IDs to their DOM elements

        // For dynamic column adjustment
        this.mainContentDefaultClasses = ['col-md-9', 'col-lg-10']; // When only left sidebar
        this.mainContentRightSidebarOpenClasses = ['col-md-6', 'col-lg-8']; // When both sidebars are open

        this.rightSidebarOpen = true; // Right sidebar starts open by default

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
        this.loadInitialData();
        setInterval(() => this.updateConnectionStatusOnly(), 10000);
        this.initTextareaAutoResize();
    }

    initTextareaAutoResize() {
        const textarea = document.getElementById('messageInput');
        if (!textarea) return;
        const initialHeight = textarea.offsetHeight > 0 ? textarea.offsetHeight : 40;
        textarea.style.minHeight = `${initialHeight}px`;

        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            let newHeight = textarea.scrollHeight;
            const maxHeight = 150; // Max height before scrolling

            if (newHeight > maxHeight) {
                newHeight = maxHeight;
                textarea.style.overflowY = 'auto';
            } else {
                textarea.style.overflowY = 'hidden';
            }
            textarea.style.height = `${newHeight}px`;
        });
    }

    async loadInitialData() {
        await this.loadStatus(); // Loads current conversation, model, params, system instruction, etc.
        await this.loadConversations(); // Loads the list of all conversations
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

        // Model settings sidebar parameter listeners
        const tempSlider = document.getElementById('temperatureInput');
        if (tempSlider) {
            tempSlider.addEventListener('input', (e) => {
                document.getElementById('temperatureValueDisplay').textContent = e.target.value;
            });
        }
        const topPSlider = document.getElementById('topPInput');
        if (topPSlider) {
            topPSlider.addEventListener('input', (e) => {
                document.getElementById('topPValueDisplay').textContent = e.target.value;
            });
        }
        // System Instruction input listener (optional, for immediate feedback if needed)
        // const systemInstructionInput = document.getElementById('systemInstructionInput');
        // if (systemInstructionInput) {
        //     systemInstructionInput.addEventListener('input', (e) => {
        //         // Potentially update a display or app state if needed on input
        //     });
        // }


        // App settings modal listeners
        document.getElementById('fontSize')?.addEventListener('input', (e) => {
            document.getElementById('fontSizeValue').textContent = e.target.value;
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

        // Delegated event listener for conversation action menus
        const conversationsList = document.getElementById('conversationsList');
        if (conversationsList) {
            conversationsList.addEventListener('click', (event) => {
                const button = event.target.closest('.three-dots-btn');
                if (button) {
                    event.stopPropagation(); // Prevent event from bubbling to parent 'a' tag for loading
                    const dropdown = button.nextElementSibling; // Assuming dropdown is the next sibling
                    const isCurrentlyShown = dropdown.classList.contains('show');

                    // Close all other dropdowns
                    document.querySelectorAll('.conversation-item-dropdown.show').forEach(d => {
                        if (d !== dropdown) d.classList.remove('show');
                    });
                    document.querySelectorAll('.three-dots-btn.active').forEach(b => {
                        if (b !== button) {
                            b.classList.remove('active');
                            b.setAttribute('aria-expanded', 'false');
                        }
                    });

                    // Toggle current dropdown
                    dropdown.classList.toggle('show', !isCurrentlyShown);
                    button.classList.toggle('active', !isCurrentlyShown);
                    button.setAttribute('aria-expanded', String(!isCurrentlyShown));
                }
            });
        }

        // Close dropdowns if clicked outside
        document.addEventListener('click', (event) => {
            if (!event.target.closest('.conversation-actions-menu')) {
                document.querySelectorAll('.conversation-item-dropdown.show').forEach(d => d.classList.remove('show'));
                document.querySelectorAll('.three-dots-btn.active').forEach(b => {
                    b.classList.remove('active');
                    b.setAttribute('aria-expanded', 'false');
                });
            }
        });
    }

    _rebuildMessageTreeRelationships() {
        // This function ensures parent-child relationships are correctly established in the messageTree
        // Useful if the tree is partially loaded or constructed from a flat list.
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
                if (!Array.isArray(parentNode.children)) parentNode.children = []; // Should be initialized above
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
                this.updateModelDisplay(data.model);
                this.streamingEnabled = data.streaming; // Server's master setting
                this.updateStreamingStatusDisplay(data.streaming);
                this.currentSystemInstruction = data.system_instruction || "You are a helpful assistant.";
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction); // Update sidebar form
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);


                const serverConversationId = data.conversation_id;
                this.currentConversationId = serverConversationId;

                if (serverConversationId && data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships(); // Ensure tree integrity
                } else if (!serverConversationId) {
                    this.messageTree = {}; // Clear tree if no active conversation
                }
                document.getElementById('conversationName').textContent = data.conversation_name || 'New Conversation';

                if (data.history && Array.isArray(data.history)) {
                    this.rebuildChatFromHistory(data.history); // Rebuilds chat from active branch history
                } else {
                    this.clearChatDisplay(); // Clear if no history
                }
            } else {
                // Handle disconnected state
                this.clearChatDisplay();
                this.messageTree = {};
                this.currentConversationId = null;
                this.updateModelSettingsSidebarForm({}, false, this.currentSystemInstruction); // Reset sidebar form
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load status:", error);
            this.updateConnectionStatus(false);
            this.clearChatDisplay();
            this.messageTree = {};
            this.currentConversationId = null;
            this.updateModelSettingsSidebarForm({}, false, this.currentSystemInstruction);
            this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
        }
    }

    updateConnectionStatusOnly() {
        // Lightweight status check, only updates connection icon
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
            if (data.conversations) {
                this.displayConversationsList(data.conversations);
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
                this.displayModelsList(data.models);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load models:", error);
            this.showAlert('Failed to load models', 'danger');
        }
    }

    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const messageContent = messageInput.value.trim();
        if (!messageContent) return;

        if (messageContent.startsWith('/')) {
            await this.handleCommand(messageContent);
            messageInput.value = '';
            messageInput.style.height = 'auto'; // Reset textarea
            return;
        }

        // Optimistically add user message to DOM
        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        // Determine the parent for the new user message from the DOM (last message in active branch)
        const parentIdForNewMessage = this.getLastMessageIdFromActiveBranchDOM();

        this.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentIdForNewMessage });
        messageInput.value = '';
        messageInput.style.height = 'auto'; // Reset textarea
        this.showThinking(true);

        // Use the streaming toggle from the right sidebar to decide if client *requests* streaming
        const clientRequestsStreaming = document.getElementById('streamingToggleRightSidebar').checked;
        const endpoint = clientRequestsStreaming ? `${this.apiBase}/api/stream` : `${this.apiBase}/api/send`;

        try {
            if (clientRequestsStreaming) {
                // Handle SSE streaming
                let fullResponseText = "";

                const response = await fetch(endpoint, { // Initial POST to send the message
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: messageContent }) // System instruction is handled server-side per conversation
                });

                if (!response.ok || !response.body) {
                    throw new Error(`Streaming request failed: ${response.statusText}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = "";

                this.showThinking(false); // Hide "thinking" once stream starts
                let tempAssistantMessageId = `msg-assistant-${Date.now()}`;
                this.addMessageToDOM('assistant', '...', tempAssistantMessageId, { parent_id: tempUserMessageId, model: "Streaming..." });


                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });

                    let boundary = buffer.indexOf("\n\n");
                    while (boundary !== -1) {
                        const chunkDataString = buffer.substring(0, boundary).replace(/^data: /, '');
                        buffer = buffer.substring(boundary + 2);
                        boundary = buffer.indexOf("\n\n");

                        try {
                            const eventData = JSON.parse(chunkDataString);
                            if (eventData.error) {
                                this.updateMessageInDOM(tempAssistantMessageId, `Error: ${eventData.error}`);
                                this.showAlert(eventData.error, 'danger');
                                return; // Stop processing stream
                            }
                            if (eventData.chunk) {
                                fullResponseText += eventData.chunk;
                                this.updateMessageInDOM(tempAssistantMessageId, fullResponseText);
                            }
                            if (eventData.done) {
                                // Final update with actual ID and metadata
                                if (this.messageElements[tempAssistantMessageId]) {
                                    this.messageElements[tempAssistantMessageId].id = eventData.message_id;
                                    this.messageElements[eventData.message_id] = this.messageElements[tempAssistantMessageId];
                                    delete this.messageElements[tempAssistantMessageId];
                                }
                                if (this.messageTree[tempAssistantMessageId]) {
                                    this.messageTree[eventData.message_id] = this.messageTree[tempAssistantMessageId];
                                    this.messageTree[eventData.message_id].id = eventData.message_id;
                                    this.messageTree[eventData.message_id].content = fullResponseText;
                                    this.messageTree[eventData.message_id].model = eventData.model;
                                    this.messageTree[eventData.message_id].token_usage = eventData.token_usage;
                                    this.messageTree[eventData.message_id].parent_id = eventData.parent_id; // Ensure parent is correct
                                    delete this.messageTree[tempAssistantMessageId];
                                } else { // If temp node wasn't created, create final one
                                    this.messageTree[eventData.message_id] = {
                                        id: eventData.message_id,
                                        role: 'assistant',
                                        content: fullResponseText,
                                        parent_id: eventData.parent_id,
                                        children: [],
                                        model: eventData.model,
                                        timestamp: new Date().toISOString(),
                                        token_usage: eventData.token_usage
                                    };
                                }
                                // Update DOM element ID and content finally
                                this.updateMessageInDOM(eventData.message_id, fullResponseText, { model: eventData.model });

                                // Update user message ID if backend provides corrected one
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
                                this.updateAllSiblingIndicators();
                                return; // Stream finished
                            }
                        } catch (e) {
                            console.warn("[WARN] Could not parse SSE event data:", chunkDataString, e);
                        }
                    }
                }
            } else {
                // Non-streaming
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: messageContent }) // System instruction handled server-side
                });
                const data = await response.json();
                this.showThinking(false);

                if (data.error) {
                    this.showAlert(data.error, 'danger');
                    this.addMessageToDOM('system', `Error: ${data.error}`);
                } else {
                    // Update user message ID if backend provides a corrected one (e.g., from DB insert)
                    // This ensures the parent_id for the assistant message is correct.
                    if (this.messageElements[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                        const tempUserMsgEl = document.getElementById(tempUserMessageId);
                        if (tempUserMsgEl) { tempUserMsgEl.id = data.parent_id; }
                        this.messageElements[data.parent_id] = this.messageElements[tempUserMessageId];
                        delete this.messageElements[tempUserMessageId];
                    }
                    if (this.messageTree[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                        this.messageTree[data.parent_id] = this.messageTree[tempUserMessageId];
                        this.messageTree[data.parent_id].id = data.parent_id; // Ensure ID is updated
                        delete this.messageTree[tempUserMessageId];
                    } else if (data.parent_id && !this.messageTree[data.parent_id] && this.messageTree[tempUserMessageId]) {
                        // If the tempUserMessageId was somehow not yet in the tree but we have a parent_id from backend
                        this.messageTree[data.parent_id] = this.messageTree[tempUserMessageId];
                        this.messageTree[data.parent_id].id = data.parent_id;
                        if (tempUserMessageId !== data.parent_id) delete this.messageTree[tempUserMessageId];
                    }


                    this.addMessageToDOM('assistant', data.response, data.message_id, {
                        model: data.model,
                        parent_id: data.parent_id, // Use parent_id from backend for assistant message
                        token_usage: data.token_usage
                    });
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
        const messageDiv = this.messageElements[messageId] || document.getElementById(messageId);
        if (!messageDiv) {
            console.warn(`[WARN] updateMessageInDOM: Message element ${messageId} not found.`);
            return;
        }

        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.innerHTML = this.formatMessageContent(newContent);
            this.applyCodeHighlighting(contentDiv);
        }

        if (newMetadata.model) {
            const modelBadge = messageDiv.querySelector('.message-header .badge.bg-secondary');
            if (modelBadge) modelBadge.textContent = newMetadata.model.split('/').pop();
        }

        if (this.messageTree[messageId]) {
            this.messageTree[messageId].content = newContent;
            if (newMetadata.model) this.messageTree[messageId].model = newMetadata.model;
            // Update other metadata in tree if needed (e.g., token_usage)
        }
        this.scrollToBottom();
    }

    getLastMessageIdFromActiveBranchDOM() {
        const chatMessagesContainer = document.getElementById('chatMessages');
        // Query for actual message rows, not just any div
        const messageElementsInDOM = chatMessagesContainer.querySelectorAll('.message-row');
        if (messageElementsInDOM.length > 0) {
            return messageElementsInDOM[messageElementsInDOM.length - 1].id;
        }
        return null; // No messages in DOM, so no parent
    }

    async handleCommand(command) {
        console.log(`[DEBUG] Handling command: ${command}`);
        if (command === '/help') {
            this.showHelp();
            return;
        }
        try {
            const response = await fetch(`${this.apiBase}/api/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command })
            });
            const data = await response.json();

            if (data.error) {
                this.showAlert(data.error, 'danger');
            } else if (data.message && !data.success) {
                this.addMessageToDOM('system', data.message); // Display non-success messages from backend
            }

            if (data.success) {
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
                if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;

                if (data.full_message_tree) { // If command returns a full tree (e.g., /load)
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships();
                }

                if (data.history && Array.isArray(data.history)) { // If command returns active branch history
                    this.rebuildChatFromHistory(data.history);
                } else if (command.startsWith('/new')) { // /new command specifically clears display
                    this.clearChatDisplay();
                    this.messageTree = {}; // Also clear the tree for a truly new conversation
                }

                if (data.model) this.updateModelDisplay(data.model);
                if (data.system_instruction !== undefined) {
                    this.currentSystemInstruction = data.system_instruction;
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                }
                if (data.params) this.updateModelSettingsSidebarForm(data.params, data.streaming !== undefined ? data.streaming : this.streamingEnabled, this.currentSystemInstruction);


                if (data.streaming !== undefined) { // Server's master streaming setting
                    this.streamingEnabled = data.streaming;
                    this.updateStreamingStatusDisplay(data.streaming); // Update main status bar
                    const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar'); // Actual toggle input
                    if (streamingToggleSidebar) streamingToggleSidebar.checked = data.streaming;
                }
                if (data.message && data.success) this.showAlert(data.message, 'info'); // Display success messages

                // Refresh conversation list if command might have changed it
                if (command.startsWith('/new') || command.startsWith('/load') || command.startsWith('/list') || command.startsWith('/save')) {
                    await this.loadConversations();
                }
            }
        } catch (error) {
            console.error("[ERROR] Command failed:", error);
            this.showAlert('Command failed', 'danger');
        }
    }

    displayConversationsList(conversations) {
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = ''; // Clear existing list
        if (!Array.isArray(conversations)) return;

        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item conversation-list-item position-relative'; // Added for menu positioning

            const createdDateObj = conv.created_at ? new Date(conv.created_at) : null;
            const createdDate = createdDateObj ? createdDateObj.toLocaleDateString([], { year: '2-digit', month: 'numeric', day: 'numeric' }) : 'N/A';

            // Use conversation_id for actions if available, otherwise filename as fallback
            const convIdentifierForActions = conv.conversation_id || conv.filename;
            // For loading, filename might be more robust if that's what backend expects
            const convIdentifierForLoading = conv.filename || conv.title;

            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" 
                   href="#" onclick="app.loadConversationByName('${convIdentifierForLoading.replace(/'/g, "\\'")}')"> 
                    <div style="max-width: calc(100% - 30px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        <strong id="conv-title-${convIdentifierForActions}">${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count || 0} messages • ${createdDate}</small>
                    </div>
                </a>
                <div class="conversation-actions-menu position-absolute end-0 me-1" style="top: 50%; transform: translateY(-50%); z-index: 10;">
                     <button class="btn btn-sm btn-light py-0 px-1 three-dots-btn" aria-expanded="false" aria-controls="dropdown-${convIdentifierForActions}" title="Conversation actions">
                         <i class="bi bi-three-dots-vertical"></i>
                     </button>
                     <div class="dropdown-menu conversation-item-dropdown p-1" id="dropdown-${convIdentifierForActions}" style="min-width: auto;">
                         <button class="dropdown-item d-flex align-items-center py-1 px-2" type="button" onclick="app.promptDuplicateConversation('${convIdentifierForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-copy me-2"></i>Duplicate</button>
                         <button class="dropdown-item d-flex align-items-center py-1 px-2" type="button" onclick="app.promptRenameConversation('${convIdentifierForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-pencil-square me-2"></i>Rename</button>
                         <div class="dropdown-divider my-1"></div>
                         <button class="dropdown-item d-flex align-items-center py-1 px-2 text-danger" type="button" onclick="app.confirmDeleteConversation('${convIdentifierForActions}', '${conv.title.replace(/'/g, "\\'")}')"><i class="bi bi-trash me-2"></i>Delete</button>
                    </div>
                </div>`;
            listElement.appendChild(li);
        });
        // Note: setupConversationActionMenus is now handled by a single delegated listener in init/setupEventListeners
    }

    displayModelsList(models) {
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = ''; // Clear existing list
        if (!Array.isArray(models)) return;

        models.forEach(model => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><code>${model.name}</code></td>
                <td>${model.display_name}</td>
                <td>${model.input_token_limit}</td>
                <td>${model.output_token_limit}</td>
                <td><button class="btn btn-sm btn-primary" onclick="app.selectModel('${model.name}')">Select</button></td>`;
            tbody.appendChild(tr);
        });
    }

    rebuildChatFromHistory(history) {
        console.log("[DEBUG] Rebuilding chat display from history array. History length:", history.length);
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = ''; // Clear current messages
        this.messageElements = {}; // Reset mapping

        if (!Array.isArray(history)) {
            if (Object.keys(this.messageTree).length === 0) { // Only show placeholder if tree is also empty
                chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
            return;
        }
        if (history.length === 0) {
            if (Object.keys(this.messageTree).length === 0) {
                chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
            this.updateAllSiblingIndicators(); // Still update indicators even if history is empty (e.g. after deleting all messages)
            return;
        }

        history.forEach(msgDataFromActiveBranch => {
            this.addMessageToDOM(
                msgDataFromActiveBranch.role,
                msgDataFromActiveBranch.content,
                msgDataFromActiveBranch.id, // Use ID from history
                { // Pass metadata
                    model: msgDataFromActiveBranch.model,
                    timestamp: msgDataFromActiveBranch.timestamp,
                    parent_id: msgDataFromActiveBranch.parent_id,
                    // token_usage could also be passed if available in history items
                }
            );
        });
        this.updateAllSiblingIndicators(); // Update indicators for all messages in the new history
    }

    async retryMessage(messageId) {
        console.log(`[DEBUG] Retrying (regenerating) assistant message: ${messageId}`);
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, { method: 'POST' });
            const data = await response.json();

            if (data.error) { this.showAlert(data.error, 'danger'); return; }

            this.currentConversationId = data.conversation_id;
            if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;
            if (data.system_instruction !== undefined) {
                 this.currentSystemInstruction = data.system_instruction;
                 this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                 this.updateModelSettingsSidebarForm(data.params || this.appSettings.params, data.streaming !== undefined ? data.streaming : this.streamingEnabled, this.currentSystemInstruction);
            }


            if (data.full_message_tree) { // Server should send the updated tree
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
            }
            if (data.history && Array.isArray(data.history)) { // Server sends new active branch history
                this.rebuildChatFromHistory(data.history);
            }
            this.showAlert('Generated new response', 'success');
        } catch (error) {
            console.error("[ERROR] Failed to retry message:", error);
            this.showAlert('Failed to retry message', 'danger');
        } finally { this.showThinking(false); }
    }

    async navigateSibling(messageId, direction) {
        console.log(`[DEBUG] Navigating (direction: ${direction}) from message: ${messageId}`);
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/navigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, direction })
            });
            const data = await response.json();

            if (data.error) { this.showAlert(data.error, 'danger'); return; }

            this.currentConversationId = data.conversation_id;
            if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;
            if (data.system_instruction !== undefined) {
                 this.currentSystemInstruction = data.system_instruction;
                 this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                 this.updateModelSettingsSidebarForm(data.params || this.appSettings.params, data.streaming !== undefined ? data.streaming : this.streamingEnabled, this.currentSystemInstruction);
            }

            if (data.full_message_tree) { // Server sends updated tree
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
            }
            if (data.history && Array.isArray(data.history)) { // Server sends new active branch history
                this.rebuildChatFromHistory(data.history);
            } else {
                this.clearChatDisplay();
                this.showAlert('Navigation resulted in empty history or no history returned.', 'warning');
            }

            if (direction !== 'none' && data.total_siblings > 1) {
                this.showAlert(`Switched to response ${data.sibling_index + 1} of ${data.total_siblings}`, 'info');
            }
        } catch (error) {
            console.error("[ERROR] Failed to navigate sibling:", error);
            this.showAlert('Failed to navigate to sibling', 'danger');
        } finally { this.showThinking(false); }
    }

    updateSiblingIndicators(parentId) {
        // Updates the "X / Y" indicator for sibling messages of a given parent.
        if (!parentId || !this.messageTree[parentId] || !Array.isArray(this.messageTree[parentId].children)) return;

        const siblings = this.messageTree[parentId].children;
        siblings.forEach((siblingId, index) => {
            const element = this.messageElements[siblingId] || document.getElementById(siblingId);
            if (element) {
                let indicatorSpan = element.querySelector('.branch-indicator');
                let indicatorTextEl = element.querySelector('.branch-indicator-text');

                if (!indicatorSpan) { // Create if doesn't exist
                    const header = element.querySelector('.message-header');
                    if (header) {
                        indicatorSpan = document.createElement('span');
                        indicatorSpan.className = 'branch-indicator badge bg-info ms-2'; // Bootstrap badge styling
                        indicatorTextEl = document.createElement('span');
                        indicatorTextEl.className = 'branch-indicator-text';
                        indicatorSpan.appendChild(indicatorTextEl);

                        // Insert after model badge or role name
                        const modelBadge = header.querySelector('.badge.bg-secondary');
                        if (modelBadge) modelBadge.insertAdjacentElement('afterend', indicatorSpan);
                        else header.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan);
                    }
                }

                if (indicatorSpan && indicatorTextEl) {
                    if (siblings.length > 1) {
                        indicatorTextEl.textContent = `${index + 1} / ${siblings.length}`;
                        indicatorSpan.style.display = 'inline-block';
                    } else {
                        indicatorSpan.style.display = 'none'; // Hide if only one child (no siblings)
                    }
                }

                // Update navigation buttons state
                const prevBtn = element.querySelector('.btn-prev-sibling');
                const nextBtn = element.querySelector('.btn-next-sibling');
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
        // Call updateSiblingIndicators for all relevant parent messages currently displayed.
        const displayedParentIds = new Set();
        Object.values(this.messageElements).forEach(domElement => {
            const messageNode = this.messageTree[domElement.id];
            if (messageNode && messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                displayedParentIds.add(messageNode.parent_id);
            }
        });
        displayedParentIds.forEach(pid => this.updateSiblingIndicators(pid));
    }

    addMessageToDOM(role, content, messageId, metadata = {}) {
        const uniqueMessageId = messageId || `msg-${role}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const contentString = (typeof content === 'string') ? content : JSON.stringify(content);

        // Add or update in the local messageTree
        if (!this.messageTree[uniqueMessageId]) {
            this.messageTree[uniqueMessageId] = {
                id: uniqueMessageId,
                role,
                content: contentString,
                parent_id: metadata.parent_id || null,
                children: [], // Initialize children array
                model: metadata.model,
                timestamp: metadata.timestamp || new Date().toISOString(),
                token_usage: metadata.token_usage || {}
            };
        } else { // Update existing node if it was a temporary one
            this.messageTree[uniqueMessageId].content = contentString;
            if (metadata.model) this.messageTree[uniqueMessageId].model = metadata.model;
            if (metadata.token_usage) this.messageTree[uniqueMessageId].token_usage = metadata.token_usage;
            // Parent ID should ideally not change for an existing message
        }

        // Link to parent in the tree
        if (metadata.parent_id && this.messageTree[metadata.parent_id]) {
            const parentNodeInTree = this.messageTree[metadata.parent_id];
            if (!Array.isArray(parentNodeInTree.children)) parentNodeInTree.children = [];
            if (!parentNodeInTree.children.includes(uniqueMessageId)) {
                parentNodeInTree.children.push(uniqueMessageId);
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const emptyState = chatMessages.querySelector('.text-center.text-muted.py-5');
        if (emptyState) emptyState.remove(); // Remove "Start a conversation" placeholder

        let messageRow = this.messageElements[uniqueMessageId]; // Check if element already exists (e.g. for streaming update)
        if (!messageRow) {
            messageRow = document.createElement('div');
            messageRow.className = `message-row message-${role}`; // CSS classes for styling
            messageRow.id = uniqueMessageId;
            chatMessages.appendChild(messageRow);
            this.messageElements[uniqueMessageId] = messageRow; // Store reference
        }

        let iconClass, roleLabel;
        switch (role) {
            case 'user':
                iconClass = 'bi-person-circle';
                roleLabel = 'You';
                break;
            case 'assistant':
                iconClass = 'bi-robot';
                roleLabel = 'CannonAI';
                break;
            default:
                iconClass = 'bi-info-circle';
                roleLabel = 'System';
                break;
        }

        const messageTimestamp = this.messageTree[uniqueMessageId]?.timestamp || new Date().toISOString();
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        let headerHTML = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && this.messageTree[uniqueMessageId]?.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${this.messageTree[uniqueMessageId].model.split('/').pop()}</span>`;
        }
        // Timestamp will be controlled by appSettings.showTimestamps via CSS class on body
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
                <div class="message-content p-2 rounded shadow-sm">
                    ${this.formatMessageContent(contentString)}
                </div>
                ${actionsHTML}
            </div>`;

        // Add placeholder for branch indicator on assistant messages
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
        this.reRenderAllMessagesVisuals(); // Apply global visual settings like avatar/timestamp visibility
        this.scrollToBottom();

        // Update sibling indicators for the parent of this new message
        if (metadata.parent_id) {
            this.updateSiblingIndicators(metadata.parent_id);
        }
        // If this new message is a user message and it already has children (e.g. loading history), update its children's indicators
        else if (role === 'user' && this.messageTree[uniqueMessageId] && this.messageTree[uniqueMessageId].children.length > 0) {
            this.updateSiblingIndicators(uniqueMessageId);
        }
    }

    formatMessageContent(content) {
        if (typeof content !== 'string') { content = String(content); }
        try { return marked.parse(content); } catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error, "Content was:", content);
            // Basic escaping for safety if markdown fails
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/\n/g, '<br>'); // Convert newlines to <br>
        }
    }

    applyCodeHighlighting(containerElement) {
        containerElement.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
            // Line numbers logic based on appSettings
            if (this.appSettings.showLineNumbers) {
                // Avoid re-adding line numbers if already present
                if (!block.classList.contains('line-numbers-active')) {
                    const lines = block.innerHTML.split('\n');
                    // Ensure the last line isn't an empty string from a trailing newline if it would create an extra number
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') ? lines.slice(0, -1) : lines;
                    const numbered = effectiveLines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                    block.innerHTML = numbered;
                    block.classList.add('line-numbers-active');
                }
            } else {
                // Remove line numbers if setting is off
                if (block.classList.contains('line-numbers-active')) {
                    block.innerHTML = block.innerHTML.replace(/<span class="line-number">.*?<\/span>/g, '');
                    block.classList.remove('line-numbers-active');
                }
            }
        });
    }

    clearChatDisplay() {
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
        this.messageElements = {}; // Clear DOM element references
        // this.messageTree should be cleared by the calling function if appropriate (e.g. /new, or if loadStatus indicates no active conv)
    }

    scrollToBottom() {
        const chatContainer = document.getElementById('chatMessages');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    showThinking(show) {
        document.getElementById('thinkingIndicator').classList.toggle('d-none', !show);
    }

    updateConnectionStatus(connected = true) {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.innerHTML = `<i class="bi bi-circle-fill ${connected ? 'text-success pulsate-connection' : 'text-danger'}"></i> ${connected ? 'Connected' : 'Disconnected'}`;
    }

    updateModelDisplay(model) {
        document.getElementById('currentModel').textContent = model ? model.split('/').pop() : 'N/A';
    }

    updateStreamingStatusDisplay(enabled) { // Reflects server's master streaming setting
        document.getElementById('streamingMode').textContent = enabled ? 'ON' : 'OFF';
    }

    updateSystemInstructionStatusDisplay(instruction) {
        const displayEl = document.getElementById('systemInstructionDisplay');
        if (displayEl) {
            const shortInstruction = instruction && instruction.length > 20 ? instruction.substring(0, 20) + "..." : (instruction || "Default");
            displayEl.textContent = shortInstruction;
            const parentStatusEl = document.getElementById('systemInstructionStatus');
            if(parentStatusEl) parentStatusEl.title = instruction || "Default System Instruction";
        }
    }


    updateModelSettingsSidebarForm(params, streamingStatus, systemInstruction) {
        // Updates the form in the right sidebar with current generation parameters
        if (!params) params = {}; // Default to empty object if no params provided

        const systemInstructionInput = document.getElementById('systemInstructionInput');
        if (systemInstructionInput) systemInstructionInput.value = systemInstruction || "You are a helpful assistant.";


        const tempSlider = document.getElementById('temperatureInput');
        if (tempSlider) {
            tempSlider.value = params.temperature !== undefined ? params.temperature : 0.7;
            document.getElementById('temperatureValueDisplay').textContent = tempSlider.value;
        }
        const maxTokensInput = document.getElementById('maxTokensInput');
        if (maxTokensInput) maxTokensInput.value = params.max_output_tokens !== undefined ? params.max_output_tokens : 800;

        const topPSlider = document.getElementById('topPInput');
        if (topPSlider) {
            topPSlider.value = params.top_p !== undefined ? params.top_p : 0.95;
            document.getElementById('topPValueDisplay').textContent = topPSlider.value;
        }
        const topKInput = document.getElementById('topKInput');
        if (topKInput) topKInput.value = params.top_k !== undefined ? params.top_k : 40;

        // Update the streaming toggle in the sidebar
        const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggleSidebar) streamingToggleSidebar.checked = streamingStatus;
    }

    showNewConversationModal() {
        document.getElementById('conversationTitle').value = ''; // Clear previous title
        this.modals.newConversation.show();
    }

    async createNewConversation() {
        const title = document.getElementById('conversationTitle').value.trim();
        try {
            // Use the /command endpoint for /new
            await this.handleCommand(`/new ${title}`);
            this.modals.newConversation.hide();
            // loadConversations will be called by handleCommand if successful
            // Also, ensure system instruction is reset/updated for the new conversation display
            // This should be handled by the response from /new command via handleCommand -> loadStatus
        } catch (error) {
            this.showAlert('Failed to create new conversation', 'danger');
        }
    }

    async loadConversationByName(conversationNameOrFilename) {
        // Use the /command endpoint for /load
        await this.handleCommand(`/load ${conversationNameOrFilename}`);
        // UI updates (chat display, tree, system instruction etc.) are handled by handleCommand's response processing
    }

    async saveConversation() {
        // Use the /command endpoint for /save
        await this.handleCommand('/save');
    }

    showModelSelector() {
        this.loadModels(); // Refresh model list before showing
        this.modals.modelSelector.show();
    }

    async selectModel(modelName) {
        // Use the /command endpoint for /model
        await this.handleCommand(`/model ${modelName}`);
        if (document.querySelector(`#modelSelectorModal.show`)) { // Check if modal is open
            this.modals.modelSelector.hide();
        }
    }

    toggleModelSettingsSidebar() {
        const sidebar = document.getElementById('modelSettingsSidebar');
        const mainContent = document.getElementById('mainContent');
        const isOpen = !sidebar.classList.contains('d-none'); // Check if currently open (i.e., d-none is NOT present)

        console.log("[DEBUG] Toggling model settings sidebar. Currently open:", isOpen);

        sidebar.classList.toggle('d-none'); // Toggle visibility
        this.rightSidebarOpen = !isOpen; // Update state: if it was open, it's now closed, and vice-versa

        if (this.rightSidebarOpen) { // Sidebar is now opening
            console.log("[DEBUG] Opening right sidebar, adjusting main content");
            mainContent.classList.remove(...this.mainContentDefaultClasses);
            mainContent.classList.add(...this.mainContentRightSidebarOpenClasses);
        } else { // Sidebar is now closing
            console.log("[DEBUG] Closing right sidebar, expanding main content");
            mainContent.classList.remove(...this.mainContentRightSidebarOpenClasses);
            mainContent.classList.add(...this.mainContentDefaultClasses);
        }
    }

    async saveModelSettingsFromSidebar() {
        const systemInstruction = document.getElementById('systemInstructionInput').value;
        const params = {
            temperature: parseFloat(document.getElementById('temperatureInput').value),
            max_output_tokens: parseInt(document.getElementById('maxTokensInput').value),
            top_p: parseFloat(document.getElementById('topPInput').value),
            top_k: parseInt(document.getElementById('topKInput').value)
            // system_instruction is now handled separately in the payload
        };
        const streaming = document.getElementById('streamingToggleRightSidebar').checked;
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params, streaming, system_instruction: systemInstruction })
            });
            const data = await response.json();
            if (data.success) {
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);
                if (data.system_instruction !== undefined) {
                    this.currentSystemInstruction = data.system_instruction;
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                }
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction);
                this.showAlert('Settings applied for current conversation', 'success');
            } else { this.showAlert(data.error || 'Failed to apply settings', 'danger'); }
        } catch (error) { this.showAlert('Failed to apply settings', 'danger'); }
    }

    async toggleStreaming() { // This toggles the server's default streaming preference
        // Use the /command endpoint for /stream
        await this.handleCommand('/stream');
        // handleCommand will update streamingEnabled and UI elements based on server response
    }

    showHistory() {
        // The history of the active branch is always displayed.
        this.showAlert('Full conversation history for the active branch is displayed in the main chat area.', 'info');
    }

    showHelp() {
        const helpContent = `
        <h5>Available Commands:</h5>
        <ul>
            <li><code>/new [title]</code> - Start a new conversation.</li>
            <li><code>/load [name/number]</code> - Load a conversation.</li>
            <li><code>/save</code> - Save the current conversation.</li>
            <li><code>/list</code> - Refresh and show saved conversations in sidebar.</li>
            <li><code>/model [model_name]</code> - Change AI model. Lists models if no name.</li>
            <li><code>/params</code> - Generation parameters & System Instruction are in the right sidebar (toggle with Params button).</li>
            <li><code>/stream</code> - Toggle server's default response streaming preference.</li>
            <li><code>/help</code> - Show this help message.</li>
        </ul>`;
        this.addMessageToDOM('system', helpContent, `help-${Date.now()}`);
    }

    // --- App Settings (Theme, Font, etc.) ---
    loadAppSettings() {
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
            // Global default system instruction is handled by backend config.
            // Client-side appSettings don't store this.
        };
        try {
            const saved = localStorage.getItem('cannonAIAppSettings');
            return saved ? { ...defaults, ...JSON.parse(saved) } : defaults;
        } catch (e) { return defaults; }
    }

    saveAppSettingsToStorage() {
        try { localStorage.setItem('cannonAIAppSettings', JSON.stringify(this.appSettings)); return true; } catch (e) { console.error("Error saving app settings:", e); return false; }
    }

    applyAppSettings() {
        this.applyTheme(this.appSettings.theme);
        document.documentElement.style.setProperty('--chat-font-size', `${this.appSettings.fontSize}px`);
        document.documentElement.style.setProperty('--chat-font-family', this.appSettings.fontFamily);

        // Toggle classes on body for settings that affect all messages
        document.body.classList.toggle('hide-timestamps', !this.appSettings.showTimestamps);
        document.body.classList.toggle('hide-avatars', !this.appSettings.showAvatars);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);

        this.updateCodeThemeLink(this.appSettings.codeTheme); // Applies syntax highlighting theme
        this.reRenderAllMessagesVisuals(); // Re-apply visuals to existing messages
    }

    applyTheme(themeName) {
        document.body.classList.remove('theme-light', 'theme-dark');
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            effectiveTheme = prefersDark ? 'dark' : 'light';
        }
        document.body.classList.add(`theme-${effectiveTheme}`);

        // Update code syntax highlighting theme based on main theme if 'default' is selected
        let codeThemeToApply = this.appSettings.codeTheme;
        if (this.appSettings.codeTheme === 'default') { // 'default' means auto-adjust with theme
            codeThemeToApply = effectiveTheme === 'dark' ? 'github-dark' : 'github';
        }
        this.updateCodeThemeLink(codeThemeToApply, false); // false to not save 'default' as the actual theme name
    }

    updateCodeThemeLink(themeName, saveSetting = true) {
        let link = document.querySelector('link[id="highlightjs-theme"]');
        if (!link) { // Create link tag if it doesn't exist
            link = document.createElement('link');
            link.id = 'highlightjs-theme';
            link.rel = 'stylesheet';
            document.head.appendChild(link);
        }
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeName}.min.css`;
        if (saveSetting) this.appSettings.codeTheme = themeName; // Save the actual applied theme name
    }

    showAppSettingsModal() {
        // Populate modal with current settings
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

        this.updatePreview(); // Update preview pane in modal
        this.modals.appSettings.show();
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
            codeTheme: document.getElementById('codeTheme').value,
            showLineNumbers: document.getElementById('showLineNumbers').checked
        };
        if (this.saveAppSettingsToStorage()) {
            this.applyAppSettings(); // Apply new settings globally
            this.showAlert('App settings saved', 'success');
            this.modals.appSettings.hide();
        } else { this.showAlert('Failed to save app settings', 'danger'); }
    }

    resetAppSettings() {
        // IMPORTANT: Replace confirm() with a custom modal for production environments
        // as confirm() can be blocked in iframes.
        if (confirm('Reset all app settings to defaults?')) {
            localStorage.removeItem('cannonAIAppSettings');
            this.appSettings = this.loadAppSettings(); // Load defaults
            this.applyAppSettings(); // Apply defaults
            this.showAppSettingsModal(); // Re-open modal to show reset state
            this.showAlert('App settings reset to defaults', 'info');
        }
    }

    updatePreview() { // Updates the preview pane in the App Settings modal
        const preview = document.getElementById('settingsPreview');
        if (!preview) return;

        // Apply font size and family
        preview.style.fontSize = `${document.getElementById('fontSize').value}px`;
        preview.style.fontFamily = document.getElementById('fontFamily').value;

        // Toggle avatar and timestamp visibility in preview
        const previewAvatar = preview.querySelector('#previewAvatar');
        if (previewAvatar) previewAvatar.style.display = document.getElementById('showAvatars').checked ? 'flex' : 'none'; // Assuming avatar is flex for centering

        const previewTimestamp = preview.querySelector('#previewTimestamp');
        if (previewTimestamp) previewTimestamp.style.display = document.getElementById('showTimestamps').checked ? 'inline' : 'none';

        // Apply theme to preview area
        const selectedThemeRadio = document.querySelector('input[name="theme"]:checked').value;
        let previewThemeClass = `theme-${selectedThemeRadio}`;
        if (selectedThemeRadio === 'auto') { // Determine auto theme for preview
            previewThemeClass = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'theme-dark' : 'theme-light';
        }
        preview.className = `preview-area border rounded p-3 ${previewThemeClass}`; // Set base classes + theme

        // Apply code theme to preview code block
        const codeBlock = preview.querySelector('pre code');
        if (codeBlock) {
            const currentCodeThemeSetting = document.getElementById('codeTheme').value;
            let themeToPreview = currentCodeThemeSetting;
            if (currentCodeThemeSetting === 'default') { // 'default' means auto-adjust with main theme
                themeToPreview = previewThemeClass.includes('theme-dark') ? 'github-dark' : 'github';
            }

            // Temporarily apply the selected highlight.js theme for preview
            // This is a bit hacky; ideally, highlight.js would re-highlight on theme change.
            // For simplicity, we might just show a static representation or rely on CSS overrides.
            // For a true preview, one would need to load the theme CSS and re-highlight.
            // The current `applyCodeHighlighting` is for the main chat, not this preview.
            // We can simulate it by setting a class on the `pre` element.
            const preElement = preview.querySelector('pre');
            if (preElement) {
                // Remove old theme classes if any, then add new one
                preElement.className = 'hljs'; // Base class for hljs
                // Add classes based on themeToPreview for styling (e.g., 'github-dark-preview')
                // This would require specific CSS for these preview themes.
            }
            // hljs.highlightElement(codeBlock); // Re-highlight if needed
        }
    }

    reRenderAllMessagesVisuals() {
        // Called when global display settings (like showAvatars, showTimestamps, codeLineNumbers) change
        // to update all existing messages in the DOM.
        document.querySelectorAll('.message-row').forEach(messageEl => {
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) avatarEl.style.display = this.appSettings.showAvatars ? 'flex' : 'none';

            const timestampEl = messageEl.querySelector('.message-timestamp-display');
            if (timestampEl) timestampEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';

            this.applyCodeHighlighting(messageEl); // Re-apply code highlighting (for line numbers)
        });
        // Apply body-level classes
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        // Theme is applied by applyTheme directly
    }

    showAlert(message, type = 'info') {
        const alertContainer = document.getElementById('alertContainer');
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show m-0 mb-2`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        alertContainer.appendChild(alertDiv);

        const bsAlert = new bootstrap.Alert(alertDiv); // Initialize Bootstrap alert
        setTimeout(() => {
            // Check if the alert still exists and is part of the DOM before trying to close
            if (bootstrap.Alert.getInstance(alertDiv)) {
                bsAlert.close();
            } else if (alertDiv.parentElement) { // Fallback if instance is gone but element remains
                alertDiv.remove();
            }
        }, 5000); // Auto-dismiss after 5 seconds
    }

    // --- New Conversation Action Methods ---
    async promptDuplicateConversation(conversationId, currentTitle) {
        // IMPORTANT: Replace prompt() with a custom modal for production environments
        const newTitle = prompt(`Enter a title for the duplicated conversation:`, `Copy of ${currentTitle}`);
        if (newTitle && newTitle.trim() !== '') {
            await this.apiDuplicateConversation(conversationId, newTitle.trim());
        }
    }

    async apiDuplicateConversation(conversationId, newTitle) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/duplicate/${conversationId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            if (data.success) {
                this.showAlert(`Conversation duplicated as "${data.new_title}"`, 'success');
                await this.loadConversations(); // Refresh conversation list
                // Optionally, you could automatically load the new conversation:
                // await this.loadConversationByName(data.new_filename || data.new_title);
            } else {
                this.showAlert(data.error || 'Failed to duplicate conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to duplicate conversation:", error);
            this.showAlert('Client-side error duplicating conversation', 'danger');
        } finally {
            this.showThinking(false);
        }
    }

    async promptRenameConversation(conversationId, currentTitle) {
        // IMPORTANT: Replace prompt() with a custom modal for production environments
        const newTitle = prompt(`Enter the new title for the conversation:`, currentTitle);
        // Proceed if newTitle is not null (user didn't cancel) and it's a non-empty string
        if (newTitle !== null && newTitle.trim() !== '') {
            if (newTitle.trim() !== currentTitle) { // Only proceed if title actually changed
                await this.apiRenameConversation(conversationId, newTitle.trim());
            }
        }
    }

    async apiRenameConversation(conversationId, newTitle) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/rename/${conversationId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            if (data.success) {
                this.showAlert(`Conversation renamed to "${data.new_title}"`, 'success');
                await this.loadConversations(); // Refresh conversation list

                // If the currently active conversation was renamed, update its name in the header
                if (this.currentConversationId === data.conversation_id) { // data.conversation_id should be the original ID
                    document.getElementById('conversationName').textContent = data.new_title;
                    // Also update in the messageTree if it's the current one
                    if (this.messageTree && this.messageTree.metadata) { // Assuming metadata is at root of messageTree
                        this.messageTree.metadata.title = data.new_title;
                    } else if (this.currentConversationId && this.messageTree[this.currentConversationId] && this.messageTree[this.currentConversationId].metadata) {
                         // If messageTree is keyed by convId and then has metadata
                        this.messageTree[this.currentConversationId].metadata.title = data.new_title;
                    }
                }
            } else {
                this.showAlert(data.error || 'Failed to rename conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to rename conversation:", error);
            this.showAlert('Client-side error renaming conversation', 'danger');
        } finally {
            this.showThinking(false);
        }
    }

    async confirmDeleteConversation(conversationId, title) {
        // IMPORTANT: Replace confirm() with a custom modal for production environments
        if (confirm(`Are you sure you want to delete the conversation "${title}"? This action cannot be undone.`)) {
            await this.apiDeleteConversation(conversationId);
        }
    }

    async apiDeleteConversation(conversationId) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/delete/${conversationId}`, {
                method: 'DELETE' // Use DELETE HTTP method
            });
            const data = await response.json();
            if (data.success) {
                this.showAlert(`Conversation deleted successfully`, 'success');
                await this.loadConversations(); // Refresh conversation list

                // If the currently active conversation was deleted, clear the chat area
                if (this.currentConversationId === data.deleted_conversation_id) {
                    this.currentConversationId = null;
                    this.clearChatDisplay();
                    document.getElementById('conversationName').textContent = 'New Conversation';
                    this.messageTree = {}; // Clear the message tree
                    // Reset system instruction to default for a "new" state
                    this.currentSystemInstruction = "You are a helpful assistant."; // Or fetch global default
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                    this.updateModelSettingsSidebarForm(this.appSettings.params || {}, this.streamingEnabled, this.currentSystemInstruction);
                }
            } else {
                this.showAlert(data.error || 'Failed to delete conversation', 'danger');
            }
        } catch (error) {
            console.error("[ERROR] Failed to delete conversation:", error);
            this.showAlert('Client-side error deleting conversation', 'danger');
        } finally {
            this.showThinking(false);
        }
    }
}

const app = new CannonAIApp(); // Initialize the app
