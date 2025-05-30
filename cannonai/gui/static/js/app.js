/**
 * CannonAI GUI - Frontend JavaScript
 * Handles all UI interactions and communication with the Flask backend
 */

class CannonAIApp {
    constructor() {
        console.log("[DEBUG] Initializing CannonAIApp");
        
        this.apiBase = window.location.origin;
        this.currentConversationId = null;
        this.streamingEnabled = false;

        this.modals = {};
        this.appSettings = this.loadAppSettings();
        this.messageTree = {};
        this.messageElements = {};

        // For dynamic column adjustment
        this.mainContentDefaultClasses = ['col-md-9', 'col-lg-10']; // When only left sidebar
        this.mainContentRightSidebarOpenClasses = ['col-md-6', 'col-lg-8']; // When both sidebars are conceptually open (lg needs to sum to 12 with left and right)
        // Adjusting for a col-lg-2 left and col-lg-2 right, main would be col-lg-8
        // For md: col-md-3 left, col-md-3 right, main col-md-6
        
        // The right sidebar starts open by default now
        this.rightSidebarOpen = true;

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

        // Since the right sidebar is now open by default, ensure main content has correct classes
        const mainContent = document.getElementById('mainContent');
        if (this.rightSidebarOpen) {
            console.log("[DEBUG] Right sidebar is open by default, adjusting main content classes");
            // Classes are already set correctly in HTML, but ensure consistency
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
        const initialHeight = textarea.offsetHeight > 0 ? textarea.offsetHeight : 40; // Min height based on CSS or default
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
                if (!parentNode.children.includes(msgId)) parentNode.children.push(msgId);
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
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);
                this.updateModelSettingsSidebarForm(data.params, data.streaming);

                const serverConversationId = data.conversation_id;
                this.currentConversationId = serverConversationId;

                if (serverConversationId && data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships();
                } else if (!serverConversationId) {
                    this.messageTree = {};
                }
                document.getElementById('conversationName').textContent = data.conversation_name || 'New Conversation';
                if (data.history && Array.isArray(data.history)) this.rebuildChatFromHistory(data.history);
                else this.clearChatDisplay();
            } else {
                this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
                this.updateModelSettingsSidebarForm({}, false);
            }
        } catch (error) {
            console.error("[ERROR] Failed to load status:", error);
            this.updateConnectionStatus(false); this.clearChatDisplay(); this.messageTree = {}; this.currentConversationId = null;
            this.updateModelSettingsSidebarForm({}, false);
        }
    }

    updateConnectionStatusOnly() {
        fetch(`${this.apiBase}/api/status`)
            .then(response => response.json())
            .then(data => this.updateConnectionStatus(data.connected))
            .catch(() => this.updateConnectionStatus(false));
    }

    async loadConversations() { /* ... (no change to this function) ... */
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

    async loadModels() { /* ... (no change to this function) ... */
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
            messageInput.value = ''; messageInput.style.height = 'auto';
            return;
        }

        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const parentIdForNewMessage = this.getLastMessageIdFromActiveBranchDOM();

        this.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentIdForNewMessage });
        messageInput.value = ''; messageInput.style.height = 'auto';
        this.showThinking(true);

        // Use the streaming toggle from the right sidebar to decide
        const useServerStreaming = document.getElementById('streamingToggleRightSidebar').checked;

        // For now, we'll simplify and use the /api/send endpoint regardless of the toggle,
        // as full SSE implementation from JS side is complex and relies on specific backend setup.
        // The 'streaming' parameter in the /api/settings can still control server's internal streaming preference.
        // This client-side toggle mainly informs the user or could be used if a true SSE client was implemented.

        const endpoint = `${this.apiBase}/api/send`; // Always use /send for simplicity here

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageContent }) // Send raw message
            });
            const data = await response.json();

            if (data.error) {
                this.showAlert(data.error, 'danger');
                this.addMessageToDOM('system', `Error: ${data.error}`);
            } else {
                if (this.messageTree[tempUserMessageId] && data.parent_id && tempUserMessageId !== data.parent_id) {
                    const tempNode = this.messageTree[tempUserMessageId]; delete this.messageTree[tempUserMessageId];
                    tempNode.id = data.parent_id; this.messageTree[data.parent_id] = tempNode;
                    const tempUserMsgEl = document.getElementById(tempUserMessageId);
                    if (tempUserMsgEl) { tempUserMsgEl.id = data.parent_id; this.messageElements[data.parent_id] = tempUserMsgEl; delete this.messageElements[tempUserMessageId];}
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
            console.error(`[ERROR] Failed to send message via ${endpoint}:`, error);
            this.showAlert('Failed to send message', 'danger');
            this.addMessageToDOM('system', `Error: connection issue or server error.`);
        } finally {
            this.showThinking(false);
        }
    }

    updateMessageInDOM(messageId, newContent, newMetadata = {}) { /* ... (no change to this function) ... */
        const messageDiv = this.messageElements[messageId];
        if (!messageDiv) return;

        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.innerHTML = this.formatMessageContent(newContent);
            this.applyCodeHighlighting(contentDiv);
        }
        if (this.messageTree[messageId]) {
            this.messageTree[messageId].content = newContent;
            if(newMetadata.model) this.messageTree[messageId].model = newMetadata.model;
            // Update other metadata in tree if needed
        }
    }

    getLastMessageIdFromActiveBranchDOM() { /* ... (no change to this function) ... */
        const chatMessagesContainer = document.getElementById('chatMessages');
        const messageElementsInDOM = chatMessagesContainer.querySelectorAll('.message-row'); // Target .message-row
        if (messageElementsInDOM.length > 0) {
            return messageElementsInDOM[messageElementsInDOM.length - 1].id;
        }
        return null;
    }

    async handleCommand(command) { /* ... (no change to this function, uses updateModelSettingsSidebarForm) ... */
        console.log(`[DEBUG] Handling command: ${command}`);
        if (command === '/help') {
            this.showHelp(); // showHelp now reflects sidebar change for /params
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
                 this.addMessageToDOM('system', data.message);
            }

            if (data.success) {
                if (data.conversation_id) this.currentConversationId = data.conversation_id;
                if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;

                if (data.full_message_tree) {
                    this.messageTree = data.full_message_tree;
                    this._rebuildMessageTreeRelationships();
                }

                if (data.history && Array.isArray(data.history)) {
                    this.rebuildChatFromHistory(data.history);
                } else if (command.startsWith('/new')) {
                    this.clearChatDisplay();
                }

                if(data.model) this.updateModelDisplay(data.model);
                // Use the updated function for sidebar
                if(data.params) this.updateModelSettingsSidebarForm(data.params, data.streaming !== undefined ? data.streaming : this.streamingEnabled);

                if(data.streaming !== undefined) {
                    this.streamingEnabled = data.streaming; // server's master setting
                    this.updateStreamingStatusDisplay(data.streaming); // main status bar
                    const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
                    if (streamingToggleSidebar) streamingToggleSidebar.checked = data.streaming; // actual toggle input
                }
                if(data.message && data.success) this.showAlert(data.message, 'info');

                if (command.startsWith('/new') || command.startsWith('/load') || command.startsWith('/list')) {
                    await this.loadConversations();
                }
            }
        } catch (error) {
            console.error("[ERROR] Command failed:", error);
            this.showAlert('Command failed', 'danger');
        }
    }

    displayConversationsList(conversations) { /* ... (no change to this function) ... */
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = '';
        if (!Array.isArray(conversations)) return;
        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item';
            const createdDate = conv.created_at ? new Date(conv.created_at).toLocaleDateString() : 'N/A';
            const loadIdentifier = conv.filename || conv.title;
            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" 
                   href="#" onclick="app.loadConversationByName('${loadIdentifier.replace(/'/g, "\\'")}')"> 
                    <div>
                        <strong>${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count || 0} messages • ${createdDate}</small>
                    </div>
                    <i class="bi bi-chevron-right"></i>
                </a>`;
            listElement.appendChild(li);
        });
    }

    displayModelsList(models) { /* ... (no change to this function) ... */
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = '';
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

    rebuildChatFromHistory(history) { /* ... (no change to this function) ... */
        console.log("[DEBUG] Rebuilding chat display from history array. History length:", history.length);
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = '';
        this.messageElements = {};

        if (!Array.isArray(history)) {
            if (Object.keys(this.messageTree).length === 0) {
                 chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
            return;
        }
        if (history.length === 0 ) {
            if (Object.keys(this.messageTree).length === 0) {
                chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
            }
             this.updateAllSiblingIndicators();
            return;
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
        this.updateAllSiblingIndicators();
    }

    async retryMessage(messageId) { /* ... (no change to this function) ... */
        console.log(`[DEBUG] Retrying (regenerating) assistant message: ${messageId}`);
        this.showThinking(true);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, { method: 'POST' });
            const data = await response.json();

            if (data.error) { this.showAlert(data.error, 'danger'); return; }
            this.currentConversationId = data.conversation_id;
            if (data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;
            if (data.full_message_tree) {
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
            }
            if (data.history && Array.isArray(data.history)) this.rebuildChatFromHistory(data.history);
            this.showAlert('Generated new response', 'success');
        } catch (error) {
            console.error("[ERROR] Failed to retry message:", error);
            this.showAlert('Failed to retry message', 'danger');
        } finally { this.showThinking(false); }
    }

    async navigateSibling(messageId, direction) { /* ... (no change to this function) ... */
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
            if(data.conversation_name) document.getElementById('conversationName').textContent = data.conversation_name;
            if (data.full_message_tree) {
                this.messageTree = data.full_message_tree;
                this._rebuildMessageTreeRelationships();
            }
            if (data.history && Array.isArray(data.history)) this.rebuildChatFromHistory(data.history);
            else { this.clearChatDisplay(); this.showAlert('Navigation resulted in empty history or no history returned.', 'warning'); }
            if (direction !== 'none' && data.total_siblings > 1) this.showAlert(`Switched to response ${data.sibling_index + 1} of ${data.total_siblings}`, 'info');
        } catch (error) {
            console.error("[ERROR] Failed to navigate sibling:", error);
            this.showAlert('Failed to navigate to sibling', 'danger');
        } finally { this.showThinking(false); }
    }

    updateSiblingIndicators(parentId) { /* ... (no change to this function) ... */
        if (!parentId || !this.messageTree[parentId] || !Array.isArray(this.messageTree[parentId].children)) return;
        const siblings = this.messageTree[parentId].children;
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
                    if (siblings.length > 1) { indicatorTextEl.textContent = `${index + 1} / ${siblings.length}`; indicatorSpan.style.display = 'inline-block'; }
                    else { indicatorSpan.style.display = 'none'; }
                }
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

    updateAllSiblingIndicators() { /* ... (no change to this function) ... */
        const displayedParentIds = new Set();
        Object.values(this.messageElements).forEach(domElement => {
            const messageNode = this.messageTree[domElement.id];
            if (messageNode && messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                displayedParentIds.add(messageNode.parent_id);
            }
        });
        displayedParentIds.forEach(pid => this.updateSiblingIndicators(pid));
    }

    addMessageToDOM(role, content, messageId, metadata = {}) { /* ... (no change to structure, CSS handles look) ... */
        const uniqueMessageId = messageId || `msg-${role}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const contentString = (typeof content === 'string') ? content : JSON.stringify(content);

        if (!this.messageTree[uniqueMessageId]) {
            this.messageTree[uniqueMessageId] = {
                id: uniqueMessageId, role, content: contentString,
                parent_id: metadata.parent_id || null, children: [],
                model: metadata.model, timestamp: metadata.timestamp || new Date().toISOString(),
            };
        }
        if (metadata.parent_id && this.messageTree[metadata.parent_id]) {
            const parentNodeInTree = this.messageTree[metadata.parent_id];
            if (!Array.isArray(parentNodeInTree.children)) parentNodeInTree.children = [];
            if (!parentNodeInTree.children.includes(uniqueMessageId)) parentNodeInTree.children.push(uniqueMessageId);
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
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit'});

        let headerHTML = `<strong>${roleLabel}</strong>`;
        if (role === 'assistant' && this.messageTree[uniqueMessageId]?.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${this.messageTree[uniqueMessageId].model.split('/').pop()}</span>`;
        }
        headerHTML += ` <span class="text-muted ms-auto">${displayTime}</span>`;

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
            <div class="message-icon me-2 ms-2 ${this.appSettings.showAvatars ? '' : 'd-none'}"><i class="bi ${iconClass} fs-4"></i></div>
            <div class="message-body">
                <div class="message-header d-flex align-items-center mb-1">${headerHTML}</div>
                <div class="message-content p-2 rounded shadow-sm">
                    ${this.formatMessageContent(contentString)}
                </div>
                ${actionsHTML}
            </div>`;

        if (role === 'assistant') {
            const headerElement = messageRow.querySelector('.message-header');
            if(headerElement) {
                const indicatorSpan = document.createElement('span');
                indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
                indicatorSpan.style.display = 'none';
                const indicatorText = document.createElement('span');
                indicatorText.className = 'branch-indicator-text';
                indicatorSpan.appendChild(indicatorText);
                const modelBadge = headerElement.querySelector('.badge.bg-secondary');
                if(modelBadge) modelBadge.insertAdjacentElement('afterend', indicatorSpan);
                else headerElement.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan);
            }
        }

        this.applyCodeHighlighting(messageRow);
        this.scrollToBottom();

        if (metadata.parent_id) this.updateSiblingIndicators(metadata.parent_id);
        else if (role === 'user' && this.messageTree[uniqueMessageId] && this.messageTree[uniqueMessageId].children.length > 0) {
            this.updateSiblingIndicators(uniqueMessageId);
        }
    }

    formatMessageContent(content) { /* ... (no change to this function) ... */
        if (typeof content !== 'string') { content = String(content); }
        try { return marked.parse(content); }
        catch (error) {
            console.error('[ERROR] Markdown parsing failed:', error, "Content was:", content);
            const escaped = content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            return escaped.replace(/\n/g, '<br>');
        }
    }

    applyCodeHighlighting(containerElement) { /* ... (no change to this function) ... */
        containerElement.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
            if (this.appSettings.showLineNumbers) {
                const lines = block.innerHTML.split('\n');
                const numbered = lines.map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`).join('\n');
                block.innerHTML = numbered;
                block.classList.add('line-numbers-active');
            } else { block.classList.remove('line-numbers-active'); }
        });
    }

    clearChatDisplay() { /* ... (no change to this function) ... */
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `<div class="text-center text-muted py-5"><i class="bi bi-chat-dots display-1"></i><p>Start a new conversation or load an existing one.</p></div>`;
        this.messageElements = {};
    }

    scrollToBottom() { /* ... (no change to this function) ... */
        const chatContainer = document.getElementById('chatMessages'); // Scroll chatMessages instead of chatContainer
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    showThinking(show) { /* ... (no change to this function) ... */
        document.getElementById('thinkingIndicator').classList.toggle('d-none', !show);
    }

    updateConnectionStatus(connected = true) { /* ... (no change to this function) ... */
        const statusEl = document.getElementById('connectionStatus');
        statusEl.innerHTML = `<i class="bi bi-circle-fill ${connected ? 'text-success pulsate-connection' : 'text-danger'}"></i> ${connected ? 'Connected' : 'Disconnected'}`;
    }

    updateModelDisplay(model) { /* ... (no change to this function) ... */
        document.getElementById('currentModel').textContent = model ? model.split('/').pop() : 'N/A';
    }

    updateStreamingStatusDisplay(enabled) { /* ... (no change to this function) ... */
        document.getElementById('streamingMode').textContent = enabled ? 'ON' : 'OFF';
    }

    updateModelSettingsSidebarForm(params, streamingStatus) {
        if (!params) params = {};
        const tempSlider = document.getElementById('temperatureInput'); // Changed ID
        if (tempSlider) {
            tempSlider.value = params.temperature !== undefined ? params.temperature : 0.7;
            document.getElementById('temperatureValueDisplay').textContent = tempSlider.value; // Changed ID
        }
        const maxTokensInput = document.getElementById('maxTokensInput'); // Changed ID
        if (maxTokensInput) maxTokensInput.value = params.max_output_tokens !== undefined ? params.max_output_tokens : 800;

        const topPSlider = document.getElementById('topPInput'); // Changed ID
        if (topPSlider) {
            topPSlider.value = params.top_p !== undefined ? params.top_p : 0.95;
            document.getElementById('topPValueDisplay').textContent = topPSlider.value; // Changed ID
        }
        const topKInput = document.getElementById('topKInput'); // Changed ID
        if (topKInput) topKInput.value = params.top_k !== undefined ? params.top_k : 40;

        const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggleSidebar) streamingToggleSidebar.checked = streamingStatus;
    }

    showNewConversationModal() { /* ... (no change to this function) ... */
        document.getElementById('conversationTitle').value = '';
        this.modals.newConversation.show();
    }

    async createNewConversation() { /* ... (no change to this function, uses updateModelSettingsSidebarForm) ... */
        const title = document.getElementById('conversationTitle').value.trim();
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/new`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title })
            });
            const data = await response.json();
            if (data.success) {
                this.currentConversationId = data.conversation_id;
                document.getElementById('conversationName').textContent = data.conversation_name;
                this.messageTree = data.full_message_tree || {}; this._rebuildMessageTreeRelationships();
                this.rebuildChatFromHistory(data.history || []);
                this.updateModelDisplay(data.model);
                this.updateModelSettingsSidebarForm(data.params, data.streaming);
                this.updateStreamingStatusDisplay(data.streaming);
                this.showAlert('New conversation started', 'success'); this.modals.newConversation.hide();
                await this.loadConversations();
            } else { this.showAlert(data.error || 'Failed to create conversation', 'danger'); }
        } catch (error) { this.showAlert('Failed to create new conversation', 'danger'); }
    }

    async loadConversationByName(conversationNameOrFilename) { /* ... (no change to this function, uses updateModelSettingsSidebarForm) ... */
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
                this.messageTree = data.full_message_tree || {}; this._rebuildMessageTreeRelationships();
                this.rebuildChatFromHistory(data.history || []);
                if(data.model) this.updateModelDisplay(data.model);
                if(data.params) this.updateModelSettingsSidebarForm(data.params, data.streaming);
                if(data.streaming !== undefined) {
                    this.streamingEnabled = data.streaming;
                    this.updateStreamingStatusDisplay(data.streaming);
                    const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
                    if (streamingToggleSidebar) streamingToggleSidebar.checked = data.streaming;
                }
            } else { this.showAlert(data.error || 'Failed to load conversation', 'danger'); }
        } catch (error) { this.showAlert('Failed to load conversation', 'danger');
        } finally { this.showThinking(false); }
    }

    async saveConversation() { /* ... (no change to this function) ... */
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/save`, { method: 'POST'});
            const data = await response.json();
            if (data.success) this.showAlert('Conversation saved', 'success');
            else this.showAlert(data.error || 'Failed to save conversation', 'danger');
        } catch (error) { this.showAlert('Failed to save conversation', 'danger');}
    }

    showModelSelector() { /* ... (no change to this function) ... */
        this.loadModels();
        this.modals.modelSelector.show();
    }

    async selectModel(modelName) { /* ... (no change to this function, uses loadStatus for params) ... */
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: modelName })
            });
            const data = await response.json();
            if (data.success) {
                this.updateModelDisplay(data.model);
                await this.loadStatus();
                this.showAlert(`Model changed to ${modelName.split('/').pop()}`, 'success');
                this.modals.modelSelector.hide();
            } else { this.showAlert(data.error || 'Failed to change model', 'danger');}
        } catch (error) { this.showAlert('Failed to change model', 'danger');}
    }

    toggleModelSettingsSidebar() {
        const sidebar = document.getElementById('modelSettingsSidebar');
        const mainContent = document.getElementById('mainContent');
        const isOpen = !sidebar.classList.contains('d-none');

        console.log("[DEBUG] Toggling model settings sidebar. Currently open:", isOpen);
        
        sidebar.classList.toggle('d-none');
        this.rightSidebarOpen = !isOpen;

        if (isOpen) { // Sidebar is now closing
            console.log("[DEBUG] Closing right sidebar, expanding main content");
            mainContent.classList.remove(...this.mainContentRightSidebarOpenClasses);
            mainContent.classList.add(...this.mainContentDefaultClasses);
        } else { // Sidebar is now opening
            console.log("[DEBUG] Opening right sidebar, adjusting main content");
            mainContent.classList.remove(...this.mainContentDefaultClasses);
            mainContent.classList.add(...this.mainContentRightSidebarOpenClasses);
        }
    }

    async saveModelSettingsFromSidebar() {
        const params = {
            temperature: parseFloat(document.getElementById('temperatureInput').value), // Changed ID
            max_output_tokens: parseInt(document.getElementById('maxTokensInput').value), // Changed ID
            top_p: parseFloat(document.getElementById('topPInput').value), // Changed ID
            top_k: parseInt(document.getElementById('topKInput').value) // Changed ID
        };
        const streaming = document.getElementById('streamingToggleRightSidebar').checked;
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
                this.updateModelSettingsSidebarForm(data.params, data.streaming);
                this.showAlert('Generation parameters applied', 'success'); // Changed message
            } else { this.showAlert(data.error || 'Failed to apply parameters', 'danger');}
        } catch (error) { this.showAlert('Failed to apply parameters', 'danger');}
    }

    async toggleStreaming() { /* ... (no change to this function logic, updates sidebar toggle) ... */
        const newServerStreamingState = !this.streamingEnabled;
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ streaming: newServerStreamingState })
            });
            const data = await response.json();
            if (data.success) {
                this.streamingEnabled = data.streaming;
                this.updateStreamingStatusDisplay(data.streaming);
                const streamingToggleSidebar = document.getElementById('streamingToggleRightSidebar');
                if (streamingToggleSidebar) streamingToggleSidebar.checked = data.streaming;
                this.showAlert(`Server streaming preference ${data.streaming ? 'enabled' : 'disabled'}`, 'success');
            } else { this.showAlert(data.error || 'Failed to toggle server streaming', 'danger');}
        } catch (error) { this.showAlert('Failed to toggle server streaming', 'danger');}
    }

    showHistory() { /* ... (no change to this function) ... */
        this.showAlert('Full conversation history for the active branch is displayed in the main chat area.', 'info');
    }

    showHelp() { /* ... (updated /params help text) ... */
        const helpContent = `
        <h5>Available Commands:</h5>
        <ul>
            <li><code>/new [title]</code> - Start a new conversation.</li>
            <li><code>/load [name/number]</code> - Load a conversation.</li>
            <li><code>/save</code> - Save the current conversation.</li>
            <li><code>/list</code> - Refresh and show saved conversations in sidebar.</li>
            <li><code>/model [model_name]</code> - Change AI model. Lists models if no name.</li>
            <li><code>/params</code> - Generation parameters are in the right sidebar (toggle with Params button).</li>
            <li><code>/stream</code> - Toggle server's default response streaming.</li>
            <li><code>/help</code> - Show this help message.</li>
        </ul>`;
        this.addMessageToDOM('system', helpContent, `help-${Date.now()}`);
    }

    loadAppSettings() { /* ... (no change to this function) ... */
        const defaults = {
            theme: 'light', fontSize: 16, fontFamily: 'system-ui',
            showTimestamps: true, showAvatars: true, enableAnimations: true,
            compactMode: false, codeTheme: 'github-dark', showLineNumbers: true
        };
        try {
            const saved = localStorage.getItem('cannonAIAppSettings');
            return saved ? { ...defaults, ...JSON.parse(saved) } : defaults;
        } catch (e) { return defaults; }
    }

    saveAppSettingsToStorage() { /* ... (no change to this function) ... */
        try { localStorage.setItem('cannonAIAppSettings', JSON.stringify(this.appSettings)); return true; }
        catch (e) { console.error("Error saving app settings:", e); return false; }
    }

    applyAppSettings() { /* ... (no change to this function) ... */
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

    applyTheme(themeName) { /* ... (no change to this function) ... */
        document.body.classList.remove('theme-light', 'theme-dark');
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            effectiveTheme = prefersDark ? 'dark' : 'light';
        }
        document.body.classList.add(`theme-${effectiveTheme}`);

        let codeThemeToApply = this.appSettings.codeTheme;
        if (this.appSettings.codeTheme === 'default') {
            codeThemeToApply = effectiveTheme === 'dark' ? 'github-dark' : 'github';
        }
        this.updateCodeThemeLink(codeThemeToApply, false);
    }

    updateCodeThemeLink(themeName, saveSetting = true) { /* ... (no change to this function) ... */
        let link = document.querySelector('link[id="highlightjs-theme"]');
        if (!link) {
            link = document.createElement('link');
            link.id = 'highlightjs-theme';
            link.rel = 'stylesheet';
            document.head.appendChild(link);
        }
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeName}.min.css`;
        if(saveSetting) this.appSettings.codeTheme = themeName;
    }

    showAppSettingsModal() { /* ... (no change to this function) ... */
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

    saveAppSettings() { /* ... (no change to this function) ... */
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
        } else { this.showAlert('Failed to save app settings', 'danger'); }
    }

    resetAppSettings() { /* ... (no change to this function) ... */
        if (confirm('Reset all app settings to defaults?')) {
            localStorage.removeItem('cannonAIAppSettings');
            this.appSettings = this.loadAppSettings();
            this.applyAppSettings();
            this.showAppSettingsModal();
            this.showAlert('App settings reset to defaults', 'info');
        }
    }

    updatePreview() { /* ... (no change to this function structure, preview HTML was updated) ... */
        const preview = document.getElementById('settingsPreview');
        if (!preview) return;
        preview.style.fontSize = `${document.getElementById('fontSize').value}px`;
        preview.style.fontFamily = document.getElementById('fontFamily').value;

        const previewAvatar = preview.querySelector('#previewAvatar');
        if(previewAvatar) previewAvatar.style.display = document.getElementById('showAvatars').checked ? 'block' : 'none';

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
            const currentCodeTheme = document.getElementById('codeTheme').value;
            let tempLink = document.getElementById('temp-preview-hljs-theme');
            if (!tempLink) {
                tempLink = document.createElement('link');
                tempLink.id = 'temp-preview-hljs-theme';
                tempLink.rel = 'stylesheet';
                document.head.appendChild(tempLink);
            }
            let themeToPreview = currentCodeTheme;
            if (currentCodeTheme === 'default') {
                 themeToPreview = previewThemeClass.includes('theme-dark') ? 'github-dark' : 'github';
            }
            tempLink.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeToPreview}.min.css`;

            const originalPreBg = preview.querySelector('pre').style.backgroundColor;
            const originalPreColor = preview.querySelector('pre code').style.color;
            if (previewThemeClass.includes('theme-dark')) {
                 preview.querySelector('pre').style.backgroundColor = '#1e1e1e';
                 preview.querySelector('pre code').style.color = '#d4d4d4';
            } else {
                 preview.querySelector('pre').style.backgroundColor = '#f8f9fa';
                 preview.querySelector('pre code').style.color = 'inherit';
            }
            hljs.highlightElement(codeBlock);
             setTimeout(() => {
                if (tempLink) tempLink.remove();
                preview.querySelector('pre').style.backgroundColor = originalPreBg;
                preview.querySelector('pre code').style.color = originalPreColor;
             }, 100);
        }
    }

    reRenderAllMessagesVisuals() { /* ... (no change to this function) ... */
        document.querySelectorAll('.message-row').forEach(messageEl => {
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) avatarEl.classList.toggle('d-none', !this.appSettings.showAvatars);

            const headerTimeEl = messageEl.querySelector('.message-header .text-muted.ms-auto');
            if(headerTimeEl) headerTimeEl.style.display = this.appSettings.showTimestamps ? 'inline' : 'none';

            this.applyCodeHighlighting(messageEl);
        });
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
    }

    showAlert(message, type = 'info') { /* ... (no change to this function) ... */
        const alertContainer = document.getElementById('alertContainer');
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
}

const app = new CannonAIApp();