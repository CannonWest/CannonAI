/**
 * Gemini Chat GUI - Frontend JavaScript
 * Handles all UI interactions and communication with the Flask backend
 */

class GeminiChatApp {
    constructor() {
        console.log("[DEBUG] Initializing GeminiChatApp");
        
        this.apiBase = window.location.origin;
        this.currentConversationId = null;
        this.streamingEnabled = false;

        this.modals = {};
        this.appSettings = this.loadAppSettings();
        this.messageTree = {}; // Master record of all messages and their relationships
        this.messageElements = {}; // Cache for DOM elements of currently displayed messages

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
        this.modals.settings = new bootstrap.Modal(document.getElementById('settingsModal'));
        this.modals.appSettings = new bootstrap.Modal(document.getElementById('appSettingsModal'));

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
    }

    async loadInitialData() {
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
        document.getElementById('temperature')?.addEventListener('input', (e) => {
            document.getElementById('temperatureValue').textContent = e.target.value;
        });
        document.getElementById('topP')?.addEventListener('input', (e) => {
            document.getElementById('topPValue').textContent = e.target.value;
        });
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
    }

    // Helper function to ensure all parent-child links are correct in this.messageTree
    _rebuildMessageTreeRelationships() {
        if (Object.keys(this.messageTree).length === 0) return;
        console.log("[DEBUG SIBLING] Rebuilding messageTree parent-child relationships internally.");

        // First, ensure all nodes have a 'children' array.
        for (const msgId in this.messageTree) {
            if (!this.messageTree[msgId].children || !Array.isArray(this.messageTree[msgId].children)) {
                this.messageTree[msgId].children = [];
            }
        }
        // Now, iterate again to populate children arrays based on parent_id
        for (const msgId in this.messageTree) {
            const messageNode = this.messageTree[msgId];
            if (messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                const parentNode = this.messageTree[messageNode.parent_id];
                // Ensure parentNode.children is an array before pushing
                if (!Array.isArray(parentNode.children)) {
                    parentNode.children = [];
                }
                if (!parentNode.children.includes(msgId)) {
                    parentNode.children.push(msgId);
                }
            }
        }
        console.log("[DEBUG SIBLING] Finished rebuilding messageTree relationships.");
    }


    async loadStatus() {
        console.log("[DEBUG] Loading client status");
        try {
            const response = await fetch(`${this.apiBase}/api/status`);
            const data = await response.json();

            this.updateConnectionStatus(data.connected);
            if (data.connected) {
                console.log("[DEBUG] Client connected, status data received.");
                this.updateModelDisplay(data.model);
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);

                const serverConversationId = data.conversation_id;
                this.currentConversationId = serverConversationId;

                if (serverConversationId && data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships(); // Ensure parent-child links are correct
                    console.log("[DEBUG] Populated and rebuilt messageTree from full_message_tree on status. Size:", Object.keys(this.messageTree).length);
                } else if (!serverConversationId) {
                    this.messageTree = {};
                    console.log("[DEBUG] No active server conversation, cleared messageTree.");
                }

                document.getElementById('conversationName').textContent = data.conversation_name || 'New Conversation';
                if (data.params) this.updateSettingsForm(data.params);

                if (data.history && Array.isArray(data.history)) {
                    console.log("[DEBUG] History received with status, rebuilding display. History length:", data.history.length);
                    this.rebuildChatFromHistory(data.history);
                } else {
                    this.clearChatDisplay();
                }
            } else {
                console.warn("[WARN] Client not connected according to status API.");
                this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
            }
        } catch (error) {
            console.error("[ERROR] Failed to load status:", error);
            this.updateConnectionStatus(false); this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
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
        console.log(`[DEBUG] Sending message: ${messageContent.substring(0, 50)}...`);

        if (messageContent.startsWith('/')) {
            await this.handleCommand(messageContent);
            messageInput.value = '';
            return;
        }

        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const parentIdForNewMessage = this.getLastMessageIdFromActiveBranchDOM();

        this.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentIdForNewMessage });
        messageInput.value = '';
        this.showThinking(true);

        try {
            const response = await fetch(`${this.apiBase}/api/send`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageContent })
            });
            const data = await response.json();

            if (data.error) {
                this.showAlert(data.error, 'danger');
                this.addMessageToDOM('system', `Error: ${data.error}`);
            } else {
                console.log('[DEBUG] Got successful response from /api/send:', data);

                if (this.messageTree[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                    console.log(`[DEBUG] Updating temp user message ID ${tempUserMessageId} to server ID ${data.parent_id}`);
                    const tempNode = this.messageTree[tempUserMessageId];
                    delete this.messageTree[tempUserMessageId];
                    tempNode.id = data.parent_id;
                    this.messageTree[data.parent_id] = tempNode;
                    const tempUserMsgEl = document.getElementById(tempUserMessageId);
                    if (tempUserMsgEl) {
                        tempUserMsgEl.id = data.parent_id;
                        this.messageElements[data.parent_id] = tempUserMsgEl;
                        delete this.messageElements[tempUserMessageId];
                    }
                } else if (data.parent_id && !this.messageTree[data.parent_id] && this.messageTree[tempUserMessageId]) {
                     this.messageTree[data.parent_id] = this.messageTree[tempUserMessageId];
                     this.messageTree[data.parent_id].id = data.parent_id;
                     if (tempUserMessageId !== data.parent_id) delete this.messageTree[tempUserMessageId];
                }

                this.addMessageToDOM('assistant', data.response, data.message_id, {
                    model: data.model,
                    parent_id: data.parent_id,
                    token_usage: data.token_usage
                });
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
            }
        } catch (error) {
            console.error("[ERROR] Failed to send message via /api/send:", error);
            this.showAlert('Failed to send message', 'danger');
            this.addMessageToDOM('system', `Error: connection issue or server error.`);
        } finally {
            this.showThinking(false);
        }
    }

    getLastMessageIdFromActiveBranchDOM() {
        const chatMessagesContainer = document.getElementById('chatMessages');
        const messageElementsInDOM = chatMessagesContainer.querySelectorAll('.message');
        if (messageElementsInDOM.length > 0) {
            return messageElementsInDOM[messageElementsInDOM.length - 1].id;
        }
        return null;
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
            } else if (data.message && !data.success) { // Simple message from command
                 this.addMessageToDOM('system', data.message);
            }

            if (data.success) { // Command resulted in a state change
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
                if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;

                if (data.full_message_tree) { // If server sends the full tree, update it
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships(); // Crucial after updating tree
                    console.log("[DEBUG] Updated and rebuilt messageTree from command response. Size:", Object.keys(this.messageTree).length);
                }

                if (data.history && Array.isArray(data.history)) {
                    this.rebuildChatFromHistory(data.history);
                } else if (command.startsWith('/new')) { // For /new, history is empty, clear display
                    this.clearChatDisplay();
                }

                if(data.model) this.updateModelDisplay(data.model);
                if(data.params) this.updateSettingsForm(data.params);
                if(data.streaming !== undefined) this.updateStreamingStatusDisplay(data.streaming);
                if(data.message && data.success) this.showAlert(data.message, 'info'); // Success message from command

                if (command.startsWith('/new') || command.startsWith('/load') || command.startsWith('/list')) {
                    await this.loadConversations(); // Refresh sidebar
                }
            }
        } catch (error) {
            console.error("[ERROR] Command failed:", error);
            this.showAlert('Command failed', 'danger');
        }
    }

    displayConversationsList(conversations) {
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = ''; // Clear existing
        if (!Array.isArray(conversations)) return;
        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item';
            const createdDate = conv.created_at ? new Date(conv.created_at).toLocaleDateString() : 'N/A';
            const loadIdentifier = conv.filename || conv.title;
            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" 
                   href="#" onclick="app.loadConversationByName('${loadIdentifier}')"> 
                    <div>
                        <strong>${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count || 0} messages • ${createdDate}</small>
                    </div>
                    <i class="bi bi-chevron-right"></i>
                </a>`;
            listElement.appendChild(li);
        });
    }

    displayModelsList(models) {
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = ''; // Clear existing
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
        // Note: this.messageTree should already be populated and relationships rebuilt by the calling function (loadStatus, loadConversationByName, etc.)

        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = '';
        this.messageElements = {};

        if (!Array.isArray(history)) {
            console.error("[ERROR] rebuildChatFromHistory received non-array history:", history);
            if (Object.keys(this.messageTree).length === 0) {
                 chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
            return;
        }

        if (history.length === 0 ) {
            if (Object.keys(this.messageTree).length === 0) { // Only show empty state if tree is also empty
                chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
        }

        history.forEach(msgDataFromActiveBranch => {
            this.addMessageToDOM(
                msgDataFromActiveBranch.role,
                msgDataFromActiveBranch.content,
                msgDataFromActiveBranch.id,
                {
                    model: msgDataFromActiveBranch.model,
                    timestamp: msgDataFromActiveBranch.timestamp,
                    parent_id: msgDataFromActiveBranch.parent_id,
                }
            );
        });

        console.log("[DEBUG] Finished DOM rebuild from history. Calling updateAllSiblingIndicators.");
        this.updateAllSiblingIndicators();
    }

    async retryMessage(messageId) {
        console.log(`[DEBUG] Retrying (regenerating) assistant message: ${messageId}`);
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, { method: 'POST' });
            const data = await response.json();
            console.log(`[DEBUG] Retry API response:`, data);

            if (data.error) {
                this.showAlert(data.error, 'danger');
                return;
            }

            this.currentConversationId = data.conversation_id;
            if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;

            if (data.full_message_tree) {
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
                console.log("[DEBUG] Updated and rebuilt messageTree from retry response. Size:", Object.keys(this.messageTree).length);
            }
            if (data.history && Array.isArray(data.history)) {
                this.rebuildChatFromHistory(data.history);
            }
            this.showAlert('Generated new response', 'success');

        } catch (error) {
            console.error("[ERROR] Failed to retry message:", error);
            this.showAlert('Failed to retry message', 'danger');
        } finally {
            this.showThinking(false);
        }
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
            console.log(`[DEBUG] Navigation API response:`, data);

            if (data.error) {
                this.showAlert(data.error, 'danger');
                return;
            }

            this.currentConversationId = data.conversation_id;
            if(data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;

            if (data.full_message_tree) {
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
                console.log("[DEBUG] Updated and rebuilt messageTree from navigate response. Size:", Object.keys(this.messageTree).length);
            }
            if (data.history && Array.isArray(data.history)) {
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
        } finally {
            this.showThinking(false);
        }
    }

    updateSiblingIndicators(parentId) {
        if (!parentId || !this.messageTree[parentId] || !Array.isArray(this.messageTree[parentId].children)) {
            // console.warn(`[DEBUG SIBLING] updateSiblingIndicators: Cannot update for parent ${parentId}. Parent or children not found/valid in messageTree.`);
            return;
        }

        const siblings = this.messageTree[parentId].children;
        // console.log(`[DEBUG SIBLING] updateSiblingIndicators for parent ${parentId}: Found ${siblings.length} children in messageTree:`, JSON.parse(JSON.stringify(siblings)));

        siblings.forEach((siblingId, index) => {
            const element = this.messageElements[siblingId];
            if (element) {
                let indicatorSpan = element.querySelector('.branch-indicator');
                let indicatorTextEl = element.querySelector('.branch-indicator-text');

                if (!indicatorSpan) {
                    const header = element.querySelector('.message-header');
                    if (header) {
                        indicatorSpan = document.createElement('span');
                        indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                        indicatorTextEl = document.createElement('span');
                        indicatorTextEl.className = 'branch-indicator-text';
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

                const prevBtn = element.querySelector('.btn-prev-sibling');
                const nextBtn = element.querySelector('.btn-next-sibling');
                if (prevBtn && nextBtn) {
                    const showNav = siblings.length > 1;
                    // console.log(`[DEBUG SIBLING] Sibling ${siblingId} (parent ${parentId}) index ${index}/${siblings.length-1}. ShowNav: ${showNav}`);
                    prevBtn.style.display = showNav ? 'inline-block' : 'none';
                    nextBtn.style.display = showNav ? 'inline-block' : 'none';
                    prevBtn.disabled = (index === 0);
                    nextBtn.disabled = (index === siblings.length - 1);
                }
            }
        });
    }

    updateAllSiblingIndicators() {
        const displayedParentIds = new Set();
        Object.values(this.messageElements).forEach(domElement => {
            const messageNode = this.messageTree[domElement.id];
            if (messageNode && messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                displayedParentIds.add(messageNode.parent_id);
            }
        });
        // console.log("[DEBUG SIBLING] Updating indicators for parents of displayed messages:", Array.from(displayedParentIds));
        displayedParentIds.forEach(pid => this.updateSiblingIndicators(pid));
    }

    addMessageToDOM(role, content, messageId, metadata = {}) {
        const uniqueMessageId = messageId || `msg-${role}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const contentString = (typeof content === 'string') ? content : JSON.stringify(content);

        let existingNode = this.messageTree[uniqueMessageId];

        if (!existingNode) {
            this.messageTree[uniqueMessageId] = {
                id: uniqueMessageId, role, content: contentString,
                parent_id: metadata.parent_id || null,
                children: [],
                model: metadata.model,
                timestamp: metadata.timestamp || new Date().toISOString(),
            };
        } else {
            this.messageTree[uniqueMessageId].content = contentString;
            this.messageTree[uniqueMessageId].timestamp = metadata.timestamp || this.messageTree[uniqueMessageId].timestamp || new Date().toISOString();
            if(metadata.model) this.messageTree[uniqueMessageId].model = metadata.model;
            if(metadata.parent_id && this.messageTree[uniqueMessageId].parent_id !== metadata.parent_id) {
                this.messageTree[uniqueMessageId].parent_id = metadata.parent_id;
            }
            if (!Array.isArray(this.messageTree[uniqueMessageId].children)) {
                this.messageTree[uniqueMessageId].children = [];
            }
        }

        if (metadata.parent_id && this.messageTree[metadata.parent_id]) {
            const parentNodeInTree = this.messageTree[metadata.parent_id];
            if (!Array.isArray(parentNodeInTree.children)) {
                parentNodeInTree.children = [];
            }
            if (!parentNodeInTree.children.includes(uniqueMessageId)) {
                parentNodeInTree.children.push(uniqueMessageId);
            }
        }

        const chatMessages = document.getElementById('chatMessages');
        const emptyState = chatMessages.querySelector('.text-center.text-muted.py-5');
        if (emptyState) emptyState.remove();

        let messageDiv = this.messageElements[uniqueMessageId];
        if (!messageDiv) {
            messageDiv = document.createElement('div');
            messageDiv.className = `message message-${role} mb-3`;
            messageDiv.id = uniqueMessageId;
            chatMessages.appendChild(messageDiv);
            this.messageElements[uniqueMessageId] = messageDiv;
        }

        let icon, roleLabel, bgClass;
        switch (role) {
            case 'user': icon = 'bi-person-circle'; roleLabel = 'You'; bgClass = 'bg-primary text-white'; break;
            case 'assistant': icon = 'bi-robot'; roleLabel = 'Gemini'; bgClass = 'bg-light'; break;
            default: icon = 'bi-info-circle'; roleLabel = 'System'; bgClass = 'bg-warning bg-opacity-25'; break;
        }

        const messageTimestamp = this.messageTree[uniqueMessageId]?.timestamp || new Date().toISOString();
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit'});

        let headerHTML = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && this.messageTree[uniqueMessageId]?.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${this.messageTree[uniqueMessageId].model.split('/').pop()}</span>`;
        }
        headerHTML += `<span class="branch-indicator badge bg-info ms-2" style="display: none;"><span class="branch-indicator-text"></span></span>`;
        headerHTML += ` <span class="text-muted ms-auto">${displayTime}</span>`;

        let actionsHTML = '';
        if (role === 'assistant') {
            actionsHTML = `
                <div class="message-actions mt-1">
                    <button class="btn btn-sm btn-outline-secondary btn-retry" onclick="app.retryMessage('${uniqueMessageId}')" title="Generate another response"><i class="bi bi-arrow-clockwise"></i> Retry</button>
                    <button class="btn btn-sm btn-outline-secondary btn-prev-sibling" onclick="app.navigateSibling('${uniqueMessageId}', 'prev')" title="Previous response" style="display: none;"><i class="bi bi-chevron-left"></i></button>
                    <button class="btn btn-sm btn-outline-secondary btn-next-sibling" onclick="app.navigateSibling('${uniqueMessageId}', 'next')" title="Next response" style="display: none;"><i class="bi bi-chevron-right"></i></button>
                </div>`;
        }

        messageDiv.innerHTML = `
            <div class="d-flex align-items-start">
                <div class="message-icon me-3 ${this.appSettings.showAvatars ? '' : 'd-none'}"><i class="bi ${icon} fs-4"></i></div>
                <div class="message-body flex-grow-1">
                    <div class="message-header d-flex align-items-center mb-1">${headerHTML}</div>
                    <div class="message-content ${bgClass} p-3 rounded">${this.formatMessageContent(contentString)}</div>
                    ${actionsHTML}
                </div>
            </div>`;

        this.applyCodeHighlighting(messageDiv);
        this.scrollToBottom();

        if (metadata.parent_id) {
            this.updateSiblingIndicators(metadata.parent_id);
        }
    }

    formatMessageContent(content) {
        if (typeof content !== 'string') {
            console.warn("[WARN] formatMessageContent received non-string content, attempting to stringify:", content);
            content = String(content);
        }
        try {
            return marked.parse(content);
        } catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error, "Content was:", content);
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/\n/g, '<br>');
        }
    }

    applyCodeHighlighting(containerElement) {
        containerElement.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
            if (this.appSettings.showLineNumbers) {
                const lines = block.innerHTML.split('\n');
                const numbered = lines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                block.innerHTML = numbered;
                block.classList.add('line-numbers-active');
            } else {
                 block.classList.remove('line-numbers-active');
            }
        });
    }

    clearChatDisplay() {
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
        this.messageElements = {};
    }

    scrollToBottom() {
        const chatContainer = document.getElementById('chatContainer');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    showThinking(show) {
        document.getElementById('thinkingIndicator').classList.toggle('d-none', !show);
    }

    updateConnectionStatus(connected = true) {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.innerHTML = `<i class="bi bi-circle-fill ${connected ? 'text-success' : 'text-danger'}"></i> ${connected ? 'Connected' : 'Disconnected'}`;
    }

    updateModelDisplay(model) {
        document.getElementById('currentModel').textContent = model ? model.split('/').pop() : 'N/A';
    }

    updateStreamingStatusDisplay(enabled) {
        document.getElementById('streamingMode').textContent = enabled ? 'ON' : 'OFF';
        const streamingToggle = document.getElementById('streamingToggle');
        if (streamingToggle) streamingToggle.checked = enabled;
    }

    updateSettingsForm(params) {
        if (!params) return;
        const tempSlider = document.getElementById('temperature');
        if (tempSlider && params.temperature !== undefined) {
            tempSlider.value = params.temperature;
            document.getElementById('temperatureValue').textContent = params.temperature;
        }
        const maxTokensInput = document.getElementById('maxTokens');
        if (maxTokensInput && params.max_output_tokens !== undefined) maxTokensInput.value = params.max_output_tokens;

        const topPSlider = document.getElementById('topP');
        if (topPSlider && params.top_p !== undefined) {
            topPSlider.value = params.top_p;
            document.getElementById('topPValue').textContent = params.top_p;
        }
        const topKInput = document.getElementById('topK');
        if (topKInput && params.top_k !== undefined) topKInput.value = params.top_k;
    }

    showNewConversationModal() {
        document.getElementById('conversationTitle').value = '';
        this.modals.newConversation.show();
    }

    async createNewConversation() {
        const title = document.getElementById('conversationTitle').value.trim();
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/new`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title })
            });
            const data = await response.json();
            if (data.success) {
                this.currentConversationId = data.conversation_id;
                document.getElementById('conversationName').textContent = data.conversation_name;
                this.messageTree = data.full_message_tree || {};
                this._rebuildMessageTreeRelationships();
                console.log("[DEBUG] Populated and rebuilt messageTree from createNewConversation. Size:", Object.keys(this.messageTree).length);
                this.rebuildChatFromHistory(data.history || []);
                this.updateModelDisplay(data.model); this.updateSettingsForm(data.params); this.updateStreamingStatusDisplay(data.streaming);
                this.showAlert('New conversation started', 'success'); this.modals.newConversation.hide();
                await this.loadConversations();
            } else { this.showAlert(data.error || 'Failed to create conversation', 'danger'); }
        } catch (error) { this.showAlert('Failed to create new conversation', 'danger'); }
    }

    async loadConversationByName(conversationNameOrFilename) {
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/load`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_name: conversationNameOrFilename })
            });
            const data = await response.json();
            if (data.success) {
                this.currentConversationId = data.conversation_id;
                document.getElementById('conversationName').textContent = data.conversation_name;
                this.messageTree = data.full_message_tree || {};
                this._rebuildMessageTreeRelationships();
                console.log("[DEBUG] Populated and rebuilt messageTree from loadConversationByName. Size:", Object.keys(this.messageTree).length);
                this.rebuildChatFromHistory(data.history || []);
                if(data.model) this.updateModelDisplay(data.model);
                if(data.params) this.updateSettingsForm(data.params);
                if(data.streaming !== undefined) this.updateStreamingStatusDisplay(data.streaming);
            } else { this.showAlert(data.error || 'Failed to load conversation', 'danger'); }
        } catch (error) { this.showAlert('Failed to load conversation', 'danger');
        } finally { this.showThinking(false); }
    }

    async saveConversation() {
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/save`, { method: 'POST'});
            const data = await response.json();
            if (data.success) this.showAlert('Conversation saved', 'success');
            else this.showAlert(data.error || 'Failed to save conversation', 'danger');
        } catch (error) { this.showAlert('Failed to save conversation', 'danger');}
    }

    showModelSelector() { this.loadModels(); this.modals.modelSelector.show(); }

    async selectModel(modelName) {
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelName })
            });
            const data = await response.json();
            if (data.success) {
                this.updateModelDisplay(data.model);
                if(data.params) this.updateSettingsForm(data.params);
                this.showAlert(`Model changed to ${modelName.split('/').pop()}`, 'success');
                this.modals.modelSelector.hide();
            } else { this.showAlert(data.error || 'Failed to change model', 'danger');}
        } catch (error) { this.showAlert('Failed to change model', 'danger');}
    }

    showSettings() {
        fetch(`${this.apiBase}/api/status`)
            .then(res => res.json())
            .then(data => {
                if (data.connected) {
                    if(data.params) this.updateSettingsForm(data.params);
                    if(data.streaming !== undefined) this.updateStreamingStatusDisplay(data.streaming);
                }
            }).catch(err => console.error("Error fetching status for settings modal:", err));
        this.modals.settings.show();
    }

    async saveSettings() {
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
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);
                this.updateSettingsForm(data.params);
                this.showAlert('Settings saved', 'success');
                this.modals.settings.hide();
            } else { this.showAlert(data.error || 'Failed to save settings', 'danger');}
        } catch (error) { this.showAlert('Failed to save settings', 'danger');}
    }

    async toggleStreaming() {
        const newStreamingState = !this.streamingEnabled;
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ streaming: newStreamingState })
            });
            const data = await response.json();
            if (data.success) {
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);
                this.showAlert(`Streaming ${data.streaming ? 'enabled' : 'disabled'}`, 'success');
            } else { this.showAlert(data.error || 'Failed to toggle streaming', 'danger');}
        } catch (error) { this.showAlert('Failed to toggle streaming', 'danger');}
    }

    showHistory() { this.showAlert('Full conversation history for the active branch is displayed in the main chat area.', 'info'); }

    showHelp() {
        const helpContent = `
        <h5>Available Commands:</h5>
        <ul>
            <li><code>/new [title]</code> - Start a new conversation.</li>
            <li><code>/load [name/number]</code> - Load a conversation.</li>
            <li><code>/save</code> - Save the current conversation.</li>
            <li><code>/list</code> - Refresh and show saved conversations in sidebar.</li>
            <li><code>/model [model_name]</code> - Change AI model (e.g., /model gemini-2.0-pro). Lists models if no name.</li>
            <li><code>/params</code> - View/Modify generation parameters (opens settings).</li>
            <li><code>/stream</code> - Toggle response streaming.</li>
            <li><code>/clear</code> - (CLI only) Clears terminal screen.</li>
            <li><code>/config</code> - (CLI only) Opens configuration wizard.</li>
            <li><code>/help</code> - Show this help message.</li>
        </ul>`;
        this.addMessageToDOM('system', helpContent, `help-${Date.now()}`);
    }

    loadAppSettings() {
        const defaults = {
            theme: 'light', fontSize: 16, fontFamily: 'system-ui',
            showTimestamps: true, showAvatars: true, enableAnimations: true,
            compactMode: false, codeTheme: 'github-dark', showLineNumbers: true
        };
        try {
            const saved = localStorage.getItem('geminiChatAppSettings');
            return saved ? { ...defaults, ...JSON.parse(saved) } : defaults;
        } catch (e) { return defaults; }
    }

    saveAppSettingsToStorage() {
        try { localStorage.setItem('geminiChatAppSettings', JSON.stringify(this.appSettings)); return true; }
        catch (e) { console.error("Error saving app settings:", e); return false; }
    }

    applyAppSettings() {
        this.applyTheme(this.appSettings.theme);
        document.documentElement.style.setProperty('--chat-font-size', `${this.appSettings.fontSize}px`);
        document.documentElement.style.setProperty('--chat-font-family', this.appSettings.fontFamily);
        document.body.classList.toggle('hide-timestamps', !this.appSettings.showTimestamps);
        document.body.classList.toggle('hide-avatars', !this.appSettings.showAvatars);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        this.updateCodeThemeLink(this.appSettings.codeTheme);
        this.reRenderAllMessagesVisuals();
    }

    applyTheme(themeName) {
        document.body.classList.remove('theme-light', 'theme-dark');
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            effectiveTheme = prefersDark ? 'dark' : 'light';
        }
        document.body.classList.add(`theme-${effectiveTheme}`);
        if (effectiveTheme === 'dark' && (this.appSettings.codeTheme === 'github' || this.appSettings.codeTheme === 'default')) {
            this.updateCodeThemeLink('github-dark');
        } else if (effectiveTheme === 'light' && (this.appSettings.codeTheme === 'github-dark' || this.appSettings.codeTheme === 'default')) {
            this.updateCodeThemeLink('github');
        } else {
             this.updateCodeThemeLink(this.appSettings.codeTheme);
        }
    }

    updateCodeThemeLink(themeName) {
        let link = document.querySelector('link[id="highlightjs-theme"]');
        if (!link) {
            link = document.createElement('link');
            link.id = 'highlightjs-theme';
            link.rel = 'stylesheet';
            document.head.appendChild(link);
        }
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeName}.min.css`;
        this.appSettings.codeTheme = themeName;
    }

    showAppSettings() {
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
        this.updatePreview();
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
            this.applyAppSettings();
            this.showAlert('App settings saved', 'success');
            this.modals.appSettings.hide();
        } else {
            this.showAlert('Failed to save app settings', 'danger');
        }
    }

    resetAppSettings() {
        if (confirm('Reset all app settings to defaults?')) {
            localStorage.removeItem('geminiChatAppSettings');
            this.appSettings = this.loadAppSettings();
            this.applyAppSettings();
            this.showAppSettings();
            this.showAlert('App settings reset to defaults', 'info');
        }
    }

    updatePreview() {
        const preview = document.getElementById('settingsPreview');
        preview.style.fontSize = `${document.getElementById('fontSize').value}px`;
        preview.style.fontFamily = document.getElementById('fontFamily').value;
        preview.querySelector('#previewAvatar').style.display = document.getElementById('showAvatars').checked ? 'block' : 'none';
        preview.querySelector('#previewTimestamp').style.display = document.getElementById('showTimestamps').checked ? 'inline' : 'none';

        const selectedThemeRadio = document.querySelector('input[name="theme"]:checked').value;
        let previewThemeClass = `theme-${selectedThemeRadio}`;
        if (selectedThemeRadio === 'auto') {
            previewThemeClass = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'theme-dark' : 'theme-light';
        }
        preview.className = `preview-area border rounded p-3 ${previewThemeClass}`;

        const codeBlock = preview.querySelector('pre code');
        if (codeBlock) {
            hljs.highlightElement(codeBlock);
        }
    }

    reRenderAllMessagesVisuals() {
        document.querySelectorAll('.message').forEach(messageEl => {
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) avatarEl.classList.toggle('d-none', !this.appSettings.showAvatars);

            const headerTimeEl = messageEl.querySelector('.message-header .text-muted.ms-auto');
            if(headerTimeEl) headerTimeEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';

            this.applyCodeHighlighting(messageEl);
        });
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
    }

    showAlert(message, type = 'info') {
        const alertContainer = document.getElementById('alertContainer');
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
        alertContainer.appendChild(alertDiv);

        const bsAlert = new bootstrap.Alert(alertDiv);

        setTimeout(() => {
            if (bootstrap.Alert.getInstance(alertDiv)) {
                 bsAlert.close();
            } else if (alertDiv.parentElement) {
                alertDiv.remove();
            }
        }, 5000);
    }
}

const app = new GeminiChatApp();
