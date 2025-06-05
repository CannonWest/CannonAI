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

        this.modelCapabilities = {};
        this.DEFAULT_MODEL_MAX_TOKENS = 8192;
        this.MIN_OUTPUT_TOKENS = 128;
        this.TOKEN_SLIDER_STEP = 128;

        this.paramChangeTimeout = null;


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
        this.modals.messageMetadata = new bootstrap.Modal(document.getElementById('messageMetadataModal'));
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
            const maxHeight = 150;

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
        await this.loadModels();
        await this.loadStatus();
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

        const debouncedSaveModelSettings = () => {
            clearTimeout(this.paramChangeTimeout);
            this.paramChangeTimeout = setTimeout(() => {
                this.saveModelSettingsFromSidebar();
            }, 500);
        };

        // Temperature Slider & Input
        const tempSlider = document.getElementById('temperatureSlider');
        const tempInput = document.getElementById('temperatureInput');
        if (tempSlider && tempInput) {
            tempSlider.addEventListener('input', () => {
                tempInput.value = parseFloat(tempSlider.value).toFixed(2);
                debouncedSaveModelSettings();
            });
            tempInput.addEventListener('change', () => { // Use 'change' for number input
                let val = parseFloat(tempInput.value);
                const min = parseFloat(tempSlider.min);
                const max = parseFloat(tempSlider.max);
                if (isNaN(val)) val = parseFloat(tempSlider.value); // Revert to slider if invalid
                if (val < min) val = min;
                if (val > max) val = max;
                val = parseFloat(val.toFixed(2)); // Ensure two decimal places

                tempInput.value = val.toFixed(2);
                tempSlider.value = val;
                this.saveModelSettingsFromSidebar(); // Direct save
            });
        }

        // Top-P Slider & Input
        const topPSlider = document.getElementById('topPSlider');
        const topPInput = document.getElementById('topPInput');
        if (topPSlider && topPInput) {
            topPSlider.addEventListener('input', () => {
                topPInput.value = parseFloat(topPSlider.value).toFixed(2);
                debouncedSaveModelSettings();
            });
            topPInput.addEventListener('change', () => {
                let val = parseFloat(topPInput.value);
                const min = parseFloat(topPSlider.min);
                const max = parseFloat(topPSlider.max);
                 if (isNaN(val)) val = parseFloat(topPSlider.value);
                if (val < min) val = min;
                if (val > max) val = max;
                val = parseFloat(val.toFixed(2));

                topPInput.value = val.toFixed(2);
                topPSlider.value = val;
                this.saveModelSettingsFromSidebar();
            });
        }

        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');

        if (maxTokensSlider && maxTokensInput) {
            maxTokensSlider.addEventListener('input', () => {
                const val = parseInt(maxTokensSlider.value);
                maxTokensInput.value = val;
                // No need for a separate display span anymore for Max Tokens
                debouncedSaveModelSettings();
            });
            maxTokensInput.addEventListener('change', () => {
                let val = parseInt(maxTokensInput.value);
                const min = parseInt(maxTokensSlider.min);
                const max = parseInt(maxTokensSlider.max);
                if (isNaN(val)) val = min;
                if (val < min) val = min;
                if (val > max) val = max;

                const step = parseInt(maxTokensSlider.step);
                if (!isNaN(val) && !isNaN(step) && step > 0) {
                    val = Math.round((val - min) / step) * step + min;
                    if (val < min) val = min;
                    if (val > max) val = max;
                }

                maxTokensInput.value = val;
                maxTokensSlider.value = val;
                this.saveModelSettingsFromSidebar();
            });
        }

        const topKInput = document.getElementById('topKInput');
        if (topKInput) {
            topKInput.addEventListener('change', () => {
                 this.saveModelSettingsFromSidebar();
            });
        }

        const streamingToggle = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggle) {
            streamingToggle.addEventListener('change', () => {
                this.saveModelSettingsFromSidebar();
            });
        }

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
        ['showTimestamps', 'showAvatars', 'enableAnimations', 'compactMode', 'showLineNumbers', 'showMetadataIcons'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.updatePreview());
        });

        const conversationsList = document.getElementById('conversationsList');
        if (conversationsList) {
            conversationsList.addEventListener('click', (event) => {
                const button = event.target.closest('.three-dots-btn');
                if (button) {
                    event.stopPropagation();
                    const dropdown = button.nextElementSibling;

                    document.querySelectorAll('.conversation-item-dropdown.show').forEach(d => {
                        if (d !== dropdown) d.classList.remove('show');
                    });
                    document.querySelectorAll('.three-dots-btn.active').forEach(b => {
                        if (b !== button) { b.classList.remove('active'); b.setAttribute('aria-expanded', 'false'); }
                    });

                    const isCurrentlyShown = dropdown.classList.contains('show');
                    dropdown.classList.toggle('show', !isCurrentlyShown);
                    button.classList.toggle('active', !isCurrentlyShown);
                    button.setAttribute('aria-expanded', String(!isCurrentlyShown));
                }
            });
        }

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

        if (Object.keys(this.messageTree).length === 0) return;


        for (const msgId in this.messageTree) {
            if (!this.messageTree[msgId].children || !Array.isArray(this.messageTree[msgId].children)) {
                this.messageTree[msgId].children = [];
            }
        }

        for (const msgId in this.messageTree) {
            const messageNode = this.messageTree[msgId];
            if (messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                const parentNode = this.messageTree[messageNode.parent_id];
                if (!Array.isArray(parentNode.children)) parentNode.children = [];
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
                this.currentModelName = data.model;
                this.updateModelDisplay(data.model);
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(this.streamingEnabled);

                this.currentSystemInstruction = data.system_instruction || "You are a helpful assistant.";
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction);
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);

                this.currentConversationId = data.conversation_id;
                if (data.conversation_id && data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships();
                } else if (!data.conversation_id) {
                    this.messageTree = {};
                }
                const convNameEl = document.getElementById('conversationName');
                if (convNameEl) convNameEl.textContent = data.conversation_name || 'New Conversation';

                if (data.history && Array.isArray(data.history)) {
                    this.rebuildChatFromHistory(data.history);
                } else {
                    this.clearChatDisplay();
                }
            } else {
                this.currentModelName = null;
                this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
                this.updateModelSettingsSidebarForm({}, false, this.currentSystemInstruction);
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
                this.modelCapabilities = {};
                data.models.forEach(model => {
                    this.modelCapabilities[model.name] = {
                        output_token_limit: model.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS,
                        input_token_limit: model.input_token_limit || 0
                    };
                });
                this.displayModelsList(data.models);
            } else {
                this.modelCapabilities = {};
            }
        } catch (error) {
            console.error("[ERROR] Failed to load models:", error);
            this.showAlert('Failed to load models', 'danger');
            this.modelCapabilities = {};
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

        const clientRequestsStreaming = document.getElementById('streamingToggleRightSidebar').checked;
        console.log(`[DEBUG] Sending message. Client requests streaming: ${clientRequestsStreaming}`);

        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const parentIdForNewMessage = this.getLastMessageIdFromActiveBranchDOM();
        this.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentIdForNewMessage });
        messageInput.value = ''; messageInput.style.height = 'auto';
        this.showThinking(true);

        const endpoint = clientRequestsStreaming ? `${this.apiBase}/api/stream` : `${this.apiBase}/api/send`;

        try {
            if (clientRequestsStreaming) {
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
                    let boundary = buffer.indexOf("\n\n");
                    while (boundary !== -1) {
                        const chunkDataString = buffer.substring(0, boundary).replace(/^data: /, '');
                        buffer = buffer.substring(boundary + 2); boundary = buffer.indexOf("\n\n");
                        try {
                            const eventData = JSON.parse(chunkDataString);
                            if (eventData.error) { this.updateMessageInDOM(tempAssistantMessageId, `Error: ${eventData.error}`); this.showAlert(eventData.error, 'danger'); return; }
                            if (eventData.chunk) { fullResponseText += eventData.chunk; this.updateMessageInDOM(tempAssistantMessageId, fullResponseText); }
                            if (eventData.done) {
                                if (this.messageElements[tempAssistantMessageId] && eventData.message_id) {
                                    this.messageElements[tempAssistantMessageId].id = eventData.message_id;
                                    this.messageElements[eventData.message_id] = this.messageElements[tempAssistantMessageId];
                                    delete this.messageElements[tempAssistantMessageId];
                                }
                                if (this.messageTree[tempAssistantMessageId] && eventData.message_id) {
                                    this.messageTree[eventData.message_id] = this.messageTree[tempAssistantMessageId];
                                    this.messageTree[eventData.message_id].id = eventData.message_id;
                                    this.messageTree[eventData.message_id].content = fullResponseText;
                                    this.messageTree[eventData.message_id].model = eventData.model;
                                    this.messageTree[eventData.message_id].token_usage = eventData.token_usage;
                                    this.messageTree[eventData.message_id].parent_id = eventData.parent_id;
                                    delete this.messageTree[tempAssistantMessageId];
                                } else if (eventData.message_id) {
                                     this.messageTree[eventData.message_id] = { id: eventData.message_id, role: 'assistant', content: fullResponseText, parent_id: eventData.parent_id, children: [], model: eventData.model, timestamp: new Date().toISOString(), token_usage: eventData.token_usage };
                                }
                                this.updateMessageInDOM(eventData.message_id, fullResponseText, { model: eventData.model });

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
                                return;
                            }
                        } catch (e) { console.warn("[WARN] Could not parse SSE event data:", chunkDataString, e); }
                    }
                }
            } else {
                const response = await fetch(endpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: messageContent })
                });
                const data = await response.json(); this.showThinking(false);
                if (data.error) { this.showAlert(data.error, 'danger'); this.addMessageToDOM('system', `Error: ${data.error}`); }
                else {
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
        const messageDiv = this.messageElements[messageId] || document.getElementById(messageId);
        if (!messageDiv) { console.warn(`[WARN] updateMessageInDOM: Message element ${messageId} not found.`); return; }

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
        }
        this.scrollToBottom();
    }

    getLastMessageIdFromActiveBranchDOM() {
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

            if (data.success) {
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
                const convNameEl = document.getElementById('conversationName');
                if (convNameEl && data.conversation_name) convNameEl.textContent = data.conversation_name;

                if (data.full_message_tree) { this.messageTree = data.full_message_tree; this._rebuildMessageTreeRelationships(); }

                if (data.history && Array.isArray(data.history)) { this.rebuildChatFromHistory(data.history); }
                else if (command.startsWith('/new')) { this.clearChatDisplay(); this.messageTree = {}; }

                if (data.model) {
                    this.currentModelName = data.model;
                    this.updateModelDisplay(data.model);
                }
                if (data.system_instruction !== undefined) {
                    this.currentSystemInstruction = data.system_instruction;
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                }
                this.updateModelSettingsSidebarForm(
                    data.params || this.appSettings.params,
                    data.streaming !== undefined ? data.streaming : this.streamingEnabled,
                    this.currentSystemInstruction
                );

                if (data.streaming !== undefined) {
                    this.streamingEnabled = data.streaming;
                    this.updateStreamingStatusDisplay(this.streamingEnabled);
                }

                if (data.message && data.success) this.showAlert(data.message, 'info');

                if (command.startsWith('/new') || command.startsWith('/load') || command.startsWith('/list') || command.startsWith('/save') || command.startsWith('/delete') || command.startsWith('/rename') || command.startsWith('/duplicate')) {
                    await this.loadConversations();
                }
            }
        } catch (error) { console.error("[ERROR] Command failed:", error); this.showAlert('Command failed', 'danger'); }
    }

    displayConversationsList(conversations) {
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = ''; if (!Array.isArray(conversations)) return;
        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item conversation-list-item position-relative';
            const createdDate = conv.created_at ? new Date(conv.created_at).toLocaleDateString([], { year: '2-digit', month: 'numeric', day: 'numeric' }) : 'N/A';
            const convIdForActions = conv.conversation_id || conv.filename;
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
        console.log("[DEBUG] Rebuilding chat display from history array. Length:", history.length);
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = '';
        this.messageElements = {};

        const placeholderHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;

        if (!Array.isArray(history) || history.length === 0) {
            if (Object.keys(this.messageTree).length === 0 ||
                (this.messageTree.metadata && Object.keys(this.messageTree.messages || {}).length === 0)) {
                chatMessages.innerHTML = placeholderHTML;
            }
            this.updateAllSiblingIndicators();
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
        this.updateAllSiblingIndicators();
    }

    async retryMessage(messageId) {
        console.log(`[DEBUG] Retrying assistant message: ${messageId}`); this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, { method: 'POST' });
            const data = await response.json();
            if (data.error) { this.showAlert(data.error, 'danger'); return; }

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

            this.showAlert('Generated new response', 'success');
        } catch (error) { console.error("[ERROR] Failed to retry message:", error); this.showAlert('Failed to retry message', 'danger'); }
        finally { this.showThinking(false); }
    }

    async navigateSibling(messageId, direction) {
        console.log(`[DEBUG] Navigating (direction: ${direction}) from message: ${messageId}`); this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/navigate`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, direction })
            });
            const data = await response.json();
            if (data.error) { this.showAlert(data.error, 'danger'); return; }

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
        if (!parentId || !this.messageTree[parentId] || !Array.isArray(this.messageTree[parentId].children)) return;

        const siblings = this.messageTree[parentId].children;
        siblings.forEach((siblingId, index) => {
            const element = this.messageElements[siblingId] || document.getElementById(siblingId);
            if (element) {
                let indicatorSpan = element.querySelector('.branch-indicator');
                let indicatorTextEl = element.querySelector('.branch-indicator-text');

                if (!indicatorSpan) {
                    const header = element.querySelector('.message-header');
                    if (header) {
                        indicatorSpan = document.createElement('span'); indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                        indicatorTextEl = document.createElement('span'); indicatorTextEl.className = 'branch-indicator-text';
                        indicatorSpan.appendChild(indicatorTextEl);

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
                        indicatorSpan.style.display = 'none';
                    }
                }

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
        const displayedParentIds = new Set();
        Object.values(this.messageElements).forEach(domEl => {
            const msgNode = this.messageTree[domEl.id];
            if (msgNode && msgNode.parent_id && this.messageTree[msgNode.parent_id]) {
                displayedParentIds.add(msgNode.parent_id);
            }
        });
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

        if (!this.messageTree[uniqueMessageId]) {
            this.messageTree[uniqueMessageId] = {
                id: uniqueMessageId, role, content: contentString, parent_id: metadata.parent_id || null, children: [],
                model: metadata.model, timestamp: metadata.timestamp || new Date().toISOString(),
                token_usage: metadata.token_usage || {}, attachments: metadata.attachments,
                ...(metadata.params && { params: metadata.params }),
                ...(metadata.branch_id && { branch_id: metadata.branch_id }),
            };
        } else {
            this.messageTree[uniqueMessageId].content = contentString;
            if (metadata.model) this.messageTree[uniqueMessageId].model = metadata.model;
            if (metadata.token_usage) this.messageTree[uniqueMessageId].token_usage = metadata.token_usage;
            if (metadata.attachments) this.messageTree[uniqueMessageId].attachments = metadata.attachments;
            if (metadata.params) this.messageTree[uniqueMessageId].params = metadata.params;
            if (metadata.branch_id) this.messageTree[uniqueMessageId].branch_id = metadata.branch_id;
        }

        if (metadata.parent_id && this.messageTree[metadata.parent_id]) {
            const parentNodeInTree = this.messageTree[metadata.parent_id];
            if (!Array.isArray(parentNodeInTree.children)) parentNodeInTree.children = [];
            if (!parentNodeInTree.children.includes(uniqueMessageId)) {
                parentNodeInTree.children.push(uniqueMessageId);
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const emptyState = chatMessages.querySelector('.text-center.text-muted.py-5');
        if (emptyState) emptyState.remove();

        let messageRow = this.messageElements[uniqueMessageId];
        if (!messageRow) {
            messageRow = document.createElement('div');
            messageRow.className = `message-row message-${role}`;
            messageRow.id = uniqueMessageId;
            chatMessages.appendChild(messageRow);
            this.messageElements[uniqueMessageId] = messageRow;
        }

        let iconClass, roleLabel;
        switch (role) {
            case 'user': iconClass = 'bi-person-circle'; roleLabel = 'You'; break;
            case 'assistant': iconClass = 'bi-robot'; roleLabel = 'CannonAI'; break;
            default: iconClass = 'bi-info-circle'; roleLabel = 'System'; break;
        }
        const messageTimestamp = this.messageTree[uniqueMessageId]?.timestamp || new Date().toISOString();
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const infoIconHTML = `
            <button class="btn btn-sm btn-message-info-icon p-0 me-2" onclick="app.showMessageMetadata('${uniqueMessageId}')" title="View Message Metadata">
                <i class="bi bi-info-circle"></i>
            </button>`;

        let headerHTML = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && this.messageTree[uniqueMessageId]?.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${this.messageTree[uniqueMessageId].model.split('/').pop()}</span>`;
        }
        headerHTML += infoIconHTML;
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

        if (role === 'assistant') {
            const headerElement = messageRow.querySelector('.message-header');
            if (headerElement) {
                const indicatorSpan = document.createElement('span');
                indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                indicatorSpan.style.display = 'none';
                const indicatorText = document.createElement('span');
                indicatorText.className = 'branch-indicator-text';
                indicatorSpan.appendChild(indicatorText);

                const modelBadge = headerElement.querySelector('.badge.bg-secondary');
                const infoIconBtn = headerElement.querySelector('.btn-message-info-icon');

                if (modelBadge) modelBadge.insertAdjacentElement('afterend', indicatorSpan);
                else if (infoIconBtn) infoIconBtn.insertAdjacentElement('afterend', indicatorSpan);
                else headerElement.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan);
            }
        }

        this.applyCodeHighlighting(messageRow);
        this.reRenderAllMessagesVisuals();
        this.scrollToBottom();

        if (metadata.parent_id) {
            this.updateSiblingIndicators(metadata.parent_id);
        }
        if (role === 'user' && this.messageTree[uniqueMessageId] && this.messageTree[uniqueMessageId].children.length > 0) {
            this.updateSiblingIndicators(uniqueMessageId);
        }
    }

    formatMessageContent(content) {
        if (typeof content !== 'string') { content = String(content); }
        try { return marked.parse(content); } catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error, "Content was:", content);
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/\n/g, '<br>');
        }
    }

    applyCodeHighlighting(containerElement) {
        containerElement.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
            if (this.appSettings.showLineNumbers) {
                if (!block.classList.contains('line-numbers-active')) {
                    const lines = block.innerHTML.split('\n');
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') ? lines.slice(0, -1) : lines;
                    block.innerHTML = effectiveLines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                    block.classList.add('line-numbers-active');
                }
            } else {
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
        this.messageElements = {};
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
        if (statusEl) statusEl.innerHTML = `<i class="bi bi-circle-fill ${connected ? 'text-success pulsate-connection' : 'text-danger'}"></i> ${connected ? 'Connected' : 'Disconnected'}`;
    }

    updateModelDisplay(modelName) {
        const modelEl = document.getElementById('currentModelDisplay');
        if (modelEl) modelEl.textContent = modelName ? modelName.split('/').pop() : 'N/A';
    }

    updateStreamingStatusDisplay(enabled) {
        const streamingModeEl = document.getElementById('streamingMode');
        if (streamingModeEl) streamingModeEl.textContent = enabled ? 'ON' : 'OFF';
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
        if (!params) params = {};

        const tempSlider = document.getElementById('temperatureSlider');
        const tempInput = document.getElementById('temperatureInput');
        if (tempSlider && tempInput) {
            const tempValue = parseFloat(params.temperature !== undefined ? params.temperature : 0.7);
            tempSlider.value = tempValue;
            tempInput.value = tempValue.toFixed(2);
        }

        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');
        // No maxTokensValueDisplay span needed anymore
        if (maxTokensSlider && maxTokensInput) {
            const currentModelMax = this.modelCapabilities[this.currentModelName]?.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS;
            maxTokensSlider.min = this.MIN_OUTPUT_TOKENS;
            maxTokensInput.min = this.MIN_OUTPUT_TOKENS;
            maxTokensSlider.max = currentModelMax;
            maxTokensInput.max = currentModelMax;
            maxTokensSlider.step = this.TOKEN_SLIDER_STEP;
            maxTokensInput.step = this.TOKEN_SLIDER_STEP;

            let currentSetValue = parseInt(params.max_output_tokens !== undefined ? params.max_output_tokens : 800);
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax;
            if (currentSetValue < this.MIN_OUTPUT_TOKENS) currentSetValue = this.MIN_OUTPUT_TOKENS;
            currentSetValue = Math.round((currentSetValue - this.MIN_OUTPUT_TOKENS) / this.TOKEN_SLIDER_STEP) * this.TOKEN_SLIDER_STEP + this.MIN_OUTPUT_TOKENS;
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax;

            maxTokensSlider.value = currentSetValue;
            maxTokensInput.value = currentSetValue;
        }

        const topPSlider = document.getElementById('topPSlider');
        const topPInput = document.getElementById('topPInput');
        if (topPSlider && topPInput) {
            const topPValue = parseFloat(params.top_p !== undefined ? params.top_p : 0.95);
            topPSlider.value = topPValue;
            topPInput.value = topPValue.toFixed(2);
        }

        const topKInputEl = document.getElementById('topKInput'); // Renamed for clarity
        if (topKInputEl) topKInputEl.value = parseInt(params.top_k !== undefined ? params.top_k : 40);

        const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggleSidebar) streamingToggleSidebar.checked = streamingStatus;
    }

    showNewConversationModal() {
        const titleInput = document.getElementById('conversationTitleInput');
        if (titleInput) titleInput.value = '';
        else console.error("Element 'conversationTitleInput' not found.");
        this.modals.newConversation.show();
    }

    async createNewConversation() {
        const titleInput = document.getElementById('conversationTitleInput');
        const title = titleInput ? titleInput.value.trim() : '';
        try {
            await this.handleCommand(`/new ${title}`);
            this.modals.newConversation.hide();
        } catch (error) { this.showAlert('Failed to create new conversation', 'danger'); }
    }

    async loadConversationByName(conversationNameOrFilename) {
        await this.handleCommand(`/load ${conversationNameOrFilename}`);
    }

    async saveConversation() { await this.handleCommand('/save'); }

    showModelSelector() {
        this.modals.modelSelector.show();
    }

    async selectModel(modelName) {
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

        const isOpen = !sidebar.classList.contains('d-none');
        sidebar.classList.toggle('d-none');
        this.rightSidebarOpen = !isOpen;

        if (this.rightSidebarOpen) {
            mainContent.classList.remove(...this.mainContentDefaultClasses);
            mainContent.classList.add(...this.mainContentRightSidebarOpenClasses);
        } else {
            mainContent.classList.remove(...this.mainContentRightSidebarOpenClasses);
            mainContent.classList.add(...this.mainContentDefaultClasses);
        }
    }

    async saveModelSettingsFromSidebar() {
        const params = {
            temperature: parseFloat(document.getElementById('temperatureInput').value),
            max_output_tokens: parseInt(document.getElementById('maxTokensInput').value),
            top_p: parseFloat(document.getElementById('topPInput').value),
            top_k: parseInt(document.getElementById('topKInput').value)
        };
        const streaming = document.getElementById('streamingToggleRightSidebar').checked;

        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params, streaming })
            });
            const data = await response.json();
            if (data.success) {
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(this.streamingEnabled);
                this.updateModelSettingsSidebarForm(data.params, data.streaming, this.currentSystemInstruction);
                this.showAlert('Session settings (params, streaming) applied', 'success');
            } else { this.showAlert(data.error || 'Failed to apply session settings', 'danger'); }
        } catch (error) { this.showAlert('Failed to apply session settings', 'danger'); }
    }

    showSystemInstructionModal() {
        const modalInput = document.getElementById('systemInstructionModalInput');
        if (modalInput) {
            modalInput.value = this.currentSystemInstruction;
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
            this.currentSystemInstruction = newInstruction;
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
                this.currentSystemInstruction = data.system_instruction;
                this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                if (this.currentConversationId && this.messageTree && this.messageTree.metadata) {
                    this.messageTree.metadata.system_instruction = data.system_instruction;
                } else if (this.currentConversationId && this.messageTree[this.currentConversationId] && this.messageTree[this.currentConversationId].metadata) {
                    this.messageTree[this.currentConversationId].metadata.system_instruction = data.system_instruction;
                } else if (this.currentConversationId && this.messageTree.messages && this.messageTree.metadata) {
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

    async toggleStreaming() { await this.handleCommand('/stream'); }

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

    loadAppSettings() {
        const defaults = {
            theme: 'light', fontSize: 16, fontFamily: 'system-ui',
            showTimestamps: true, showAvatars: true, enableAnimations: true,
            compactMode: false, codeTheme: 'github-dark', showLineNumbers: true,
            showMetadataIcons: true,
            defaultSystemInstruction: "You are a helpful assistant.",
            params: { temperature: 0.7, max_output_tokens: 800, top_p: 0.95, top_k: 40 }
        };
        try {
            const saved = localStorage.getItem('cannonAIAppSettings');
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
        document.body.classList.toggle('hide-metadata-icons', !this.appSettings.showMetadataIcons);
        this.updateCodeThemeLink(this.appSettings.codeTheme);
        this.reRenderAllMessagesVisuals();
    }
    applyTheme(themeName) {
        document.body.classList.remove('theme-light', 'theme-dark');
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        document.body.classList.add(`theme-${effectiveTheme}`);

        let codeThemeToApply = this.appSettings.codeTheme;
        if (this.appSettings.codeTheme === 'default') {
            codeThemeToApply = effectiveTheme === 'dark' ? 'github-dark' : 'github';
        }
        this.updateCodeThemeLink(codeThemeToApply, false);
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
        if (saveSetting) this.appSettings.codeTheme = themeName;
        document.querySelectorAll('pre code').forEach(block => {
            const parentPre = block.closest('pre');
            if (parentPre) {
                 const tempContent = block.textContent;
                 block.className = `language-${block.className.match(/language-(\S+)/)?.[1] || 'plaintext'} hljs`;
                 block.innerHTML = tempContent;
                 hljs.highlightElement(block);
                 this.applyCodeHighlighting(parentPre);
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
        document.getElementById('showMetadataIcons').checked = this.appSettings.showMetadataIcons;
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
            showMetadataIcons: document.getElementById('showMetadataIcons').checked,
            enableAnimations: document.getElementById('enableAnimations').checked,
            compactMode: document.getElementById('compactMode').checked,
            codeTheme: document.getElementById('codeTheme').value,
            showLineNumbers: document.getElementById('showLineNumbers').checked,
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
            this.appSettings = this.loadAppSettings();
            this.applyAppSettings();
            this.showAppSettingsModal();
            this.showAlert('App settings reset to defaults', 'info');
        }
    }
    updatePreview() {
        const preview = document.getElementById('settingsPreview'); if (!preview) return;
        preview.style.fontSize = `${document.getElementById('fontSize').value}px`;
        preview.style.fontFamily = document.getElementById('fontFamily').value;

        const previewAvatarContainer = preview.querySelector('#previewAvatarContainer');
        if(previewAvatarContainer) previewAvatarContainer.style.display = document.getElementById('showAvatars').checked ? 'flex' : 'none';

        const previewMetadataIcon = preview.querySelector('.btn-message-info-icon');
        if(previewMetadataIcon) previewMetadataIcon.style.display = document.getElementById('showMetadataIcons').checked ? 'inline-block' : 'none';

        const previewTimestamp = preview.querySelector('#previewTimestamp');
        if(previewTimestamp) previewTimestamp.style.display = document.getElementById('showTimestamps').checked ? 'inline' : 'none';

        const selectedThemeRadio = document.querySelector('input[name="theme"]:checked').value;
        let previewThemeClass = `theme-${selectedThemeRadio}`;
        if (selectedThemeRadio === 'auto') {
            previewThemeClass = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'theme-dark' : 'theme-light';
        }
        preview.className = `preview-area border rounded p-3 ${previewThemeClass}`;

        const codeBlock = preview.querySelector('pre code');
        if (codeBlock) {
            let selectedCodeTheme = document.getElementById('codeTheme').value;
            if (selectedCodeTheme === 'default') {
                selectedCodeTheme = (previewThemeClass === 'theme-dark') ? 'github-dark' : 'github';
            }
             hljs.highlightElement(codeBlock);
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
        document.querySelectorAll('.message-row').forEach(messageEl => {
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) avatarEl.style.display = this.appSettings.showAvatars ? 'flex' : 'none';

            const timestampEl = messageEl.querySelector('.message-timestamp-display');
            if (timestampEl) timestampEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';

            const metadataIconEl = messageEl.querySelector('.btn-message-info-icon');
             if (metadataIconEl) metadataIconEl.style.display = this.appSettings.showMetadataIcons ? 'inline-block' : 'none';

            this.applyCodeHighlighting(messageEl);
        });
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('hide-metadata-icons', !this.appSettings.showMetadataIcons);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
    }
    showAlert(message, type = 'info') {
        const alertContainer = document.getElementById('alertContainer');
        if (!alertContainer) return;
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show m-0 mb-2`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        alertContainer.appendChild(alertDiv);
        const bsAlert = new bootstrap.Alert(alertDiv);
        setTimeout(() => {
            if (bootstrap.Alert.getInstance(alertDiv)) bsAlert.close();
            else if (alertDiv.parentElement) alertDiv.remove();
        }, 5000);
    }

    async promptDuplicateConversation(conversationId, currentTitle) {
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
                await this.loadConversations();
                if (this.currentConversationId === data.conversation_id) {
                    const convNameEl = document.getElementById('conversationName');
                    if(convNameEl) convNameEl.textContent = data.new_title;
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
                await this.loadConversations();
                if (this.currentConversationId === data.deleted_conversation_id) {
                    this.currentConversationId = null;
                    this.clearChatDisplay();
                    this.messageTree = {};
                    const convNameEl = document.getElementById('conversationName');
                    if(convNameEl) convNameEl.textContent = 'New Conversation';
                    this.currentSystemInstruction = this.appSettings.defaultSystemInstruction || "You are a helpful assistant.";
                    this.updateSystemInstructionStatusDisplay(this.currentSystemInstruction);
                    this.updateModelSettingsSidebarForm(
                        this.appSettings.params || {},
                        this.streamingEnabled,
                        this.currentSystemInstruction
                    );
                }
            } else { this.showAlert(data.error || 'Failed to delete conversation', 'danger'); }
        } catch (error) { console.error("[ERROR] Failed to delete:", error); this.showAlert('Client error deleting conversation', 'danger'); }
        finally { this.showThinking(false); }
    }

    showMessageMetadata(messageId) {
        const messageData = this.messageTree[messageId];
        if (!messageData) {
            this.showAlert('Could not find metadata for this message.', 'warning');
            return;
        }
        const metadataContentEl = document.getElementById('messageMetadataContent');
        if (metadataContentEl) {
            const displayData = { ...messageData };
            metadataContentEl.textContent = JSON.stringify(displayData, null, 2);
            hljs.highlightElement(metadataContentEl);
        }
        this.modals.messageMetadata.show();
    }

    copyMetadataToClipboard() {
        const metadataContentEl = document.getElementById('messageMetadataContent');
        if (metadataContentEl && navigator.clipboard) {
            navigator.clipboard.writeText(metadataContentEl.textContent)
                .then(() => this.showAlert('Metadata copied to clipboard!', 'success'))
                .catch(err => {
                    console.error('Failed to copy metadata: ', err);
                    this.showAlert('Failed to copy metadata.', 'danger');
                });
        } else if (metadataContentEl) {
            const textarea = document.createElement('textarea');
            textarea.value = metadataContentEl.textContent;
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                this.showAlert('Metadata copied to clipboard! (fallback)', 'success');
            } catch (err) {
                console.error('Fallback copy failed: ', err);
                this.showAlert('Failed to copy metadata (fallback).', 'danger');
            }
            document.body.removeChild(textarea);
        }
    }
}

const app = new CannonAIApp();

