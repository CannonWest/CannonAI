/**
 * CannonAI Main Application
 * Orchestrates all modules and provides the main application interface
 */

// Import all modules
import { APIClient } from './modules/apiClient.js';
import { MessageRenderer } from './modules/messageRenderer.js';
import { ConversationManager } from './modules/conversationManager.js';
import { SettingsManager } from './modules/settingsManager.js';
import { UIComponents } from './modules/uiComponents.js';
import { CommandHandler } from './modules/commandHandler.js';

class CannonAIApp {
    constructor() {
        console.log("[App] Initializing CannonAI Application");
        
        // Initialize modules
        this.api = new APIClient(window.location.origin);
        this.settings = new SettingsManager();
        this.ui = new UIComponents();
        this.conversations = new ConversationManager();
        this.messages = new MessageRenderer();
        this.commands = new CommandHandler(
            this.api,
            this.conversations,
            this.messages,
            this.ui
        );
        
        // Store reference to app instance globally for HTML event handlers
        window.app = this;
        
        // Initialize when DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.init());
        } else {
            this.init();
        }
    }

    init() {
        console.log("[App] DOM ready, initializing application");
        
        // Apply saved settings
        this.settings.applySettings();
        
        // Initialize UI components
        this.ui.initTextareaAutoResize();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Load initial data
        this.loadInitialData();
        
        // Setup periodic status check
        setInterval(() => this.updateConnectionStatusOnly(), 10000);
        
        // Set initial sidebar state
        const mainContent = document.getElementById('mainContent');
        if (this.ui.rightSidebarOpen && mainContent) {
            mainContent.classList.remove(...this.ui.mainContentDefaultClasses);
            mainContent.classList.add(...this.ui.mainContentRightSidebarOpenClasses);
        }
        
        console.log("[App] Application initialization complete");
    }

    setupEventListeners() {
        console.log("[App] Setting up event listeners");
        
        // Message input
        const messageInput = document.getElementById('messageInput');
        messageInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Debounced save for model settings
        const debouncedSaveModelSettings = () => {
            clearTimeout(this.settings.paramChangeTimeout);
            this.settings.paramChangeTimeout = setTimeout(() => {
                this.saveModelSettingsFromSidebar();
            }, 500);
        };

        // Temperature controls
        const tempSlider = document.getElementById('temperatureSlider');
        const tempInput = document.getElementById('temperatureInput');
        if (tempSlider && tempInput) {
            tempSlider.addEventListener('input', () => {
                tempInput.value = parseFloat(tempSlider.value).toFixed(2);
                debouncedSaveModelSettings();
            });
            tempInput.addEventListener('change', () => {
                let val = parseFloat(tempInput.value);
                const min = parseFloat(tempSlider.min);
                const max = parseFloat(tempSlider.max);
                if (isNaN(val)) val = parseFloat(tempSlider.value);
                if (val < min) val = min;
                if (val > max) val = max;
                val = parseFloat(val.toFixed(2));
                tempInput.value = val.toFixed(2);
                tempSlider.value = val;
                this.saveModelSettingsFromSidebar();
            });
        }

        // Top-P controls
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

        // Max tokens controls
        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');
        if (maxTokensSlider && maxTokensInput) {
            maxTokensSlider.addEventListener('input', () => {
                const val = parseInt(maxTokensSlider.value);
                maxTokensInput.value = val;
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

        // Top-K control
        const topKInput = document.getElementById('topKInput');
        topKInput?.addEventListener('change', () => {
            this.saveModelSettingsFromSidebar();
        });

        // Streaming toggle
        const streamingToggle = document.getElementById('streamingToggleRightSidebar');
        streamingToggle?.addEventListener('change', () => {
            this.saveModelSettingsFromSidebar();
        });

        // App settings controls
        document.getElementById('fontSize')?.addEventListener('input', (e) => {
            const display = document.getElementById('fontSizeValue');
            if (display) display.textContent = e.target.value;
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

        // Conversation dropdown menus
        const conversationsList = document.getElementById('conversationsList');
        if (conversationsList) {
            conversationsList.addEventListener('click', (event) => {
                const button = event.target.closest('.three-dots-btn');
                if (button) {
                    event.stopPropagation();
                    const dropdown = button.nextElementSibling;

                    // Close other dropdowns
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
                    const isCurrentlyShown = dropdown.classList.contains('show');
                    dropdown.classList.toggle('show', !isCurrentlyShown);
                    button.classList.toggle('active', !isCurrentlyShown);
                    button.setAttribute('aria-expanded', String(!isCurrentlyShown));
                }
            });
        }

        // Click outside to close dropdowns
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

    async loadInitialData() {
        console.log("[App] Loading initial data");
        await this.loadModels();
        await this.loadStatus();
        await this.loadConversations();
    }

    async loadModels() {
        console.log("[App] Loading available models");
        try {
            const data = await this.api.getModels();
            if (data.models && Array.isArray(data.models)) {
                this.settings.updateModelCapabilities(data.models);
                this.displayModelsList(data.models);
            }
        } catch (error) {
            console.error("[App] Failed to load models:", error);
            this.ui.showAlert('Failed to load models', 'danger');
        }
    }

    async loadStatus() {
        console.log("[App] Loading client status");
        try {
            const data = await this.api.getStatus();
            this.ui.updateConnectionStatus(data.connected);

            if (data.connected) {
                // Update current state
                this.settings.setCurrentModel(data.model);
                this.settings.streamingEnabled = data.streaming;
                this.ui.updateStreamingStatus(data.streaming);

                this.conversations.currentSystemInstruction = data.system_instruction || "You are a helpful assistant.";
                this.ui.updateSystemInstructionDisplay(this.conversations.currentSystemInstruction);

                this.settings.updateModelSettingsForm(data.params, data.streaming, this.conversations.currentSystemInstruction);

                // Update conversation data
                this.conversations.setCurrentConversation(data.conversation_id, data.conversation_name);
                if (data.conversation_id && data.full_message_tree) {
                    this.conversations.updateMessageTree(data.full_message_tree);
                } else if (!data.conversation_id) {
                    this.conversations.clearConversation();
                }

                // Rebuild chat display
                if (data.history && Array.isArray(data.history)) {
                    this.messages.rebuildChatFromHistory(data.history);
                } else {
                    this.messages.clearChatDisplay();
                }
            } else {
                // Not connected - clear everything
                this.settings.setCurrentModel(null);
                this.messages.clearChatDisplay();
                this.conversations.clearConversation();
                this.settings.updateModelSettingsForm({}, false, this.conversations.currentSystemInstruction);
                this.ui.updateSystemInstructionDisplay(this.conversations.currentSystemInstruction);
            }
        } catch (error) {
            console.error("[App] Failed to load status:", error);
            this.ui.updateConnectionStatus(false);
            this.settings.setCurrentModel(null);
            this.messages.clearChatDisplay();
            this.conversations.clearConversation();
        }
    }

    async loadConversations() {
        console.log("[App] Loading conversations list");
        try {
            const data = await this.api.getConversations();
            if (data.conversations) {
                this.displayConversationsList(data.conversations);
            }
        } catch (error) {
            console.error("[App] Failed to load conversations:", error);
        }
    }

    updateConnectionStatusOnly() {
        console.log("[App] Checking connection status");
        this.api.getStatus()
            .then(data => this.ui.updateConnectionStatus(data.connected))
            .catch(() => this.ui.updateConnectionStatus(false));
    }

    // ============ Message Handling ============

    async sendMessage() {
        console.log("[App] Sending message");
        
        const messageInput = document.getElementById('messageInput');
        const messageContent = messageInput.value.trim();
        if (!messageContent) return;

        // Handle commands
        if (messageContent.startsWith('/')) {
            await this.handleCommand(messageContent);
            messageInput.value = '';
            messageInput.style.height = 'auto';
            return;
        }

        // Regular message
        const clientRequestsStreaming = document.getElementById('streamingToggleRightSidebar').checked;
        console.log(`[App] Sending message. Streaming: ${clientRequestsStreaming}`);

        // Create temporary user message
        const tempUserMessageId = `msg-user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const parentId = this.conversations.getLastMessageIdFromActiveBranch();
        
        this.messages.addMessageToDOM('user', messageContent, tempUserMessageId, { parent_id: parentId });
        this.conversations.addMessageToTree(tempUserMessageId, {
            role: 'user',
            content: messageContent,
            parent_id: parentId
        });

        messageInput.value = '';
        messageInput.style.height = 'auto';
        this.ui.showThinking(true);

        try {
            if (clientRequestsStreaming) {
                await this.handleStreamingMessage(messageContent, tempUserMessageId);
            } else {
                await this.handleNonStreamingMessage(messageContent, tempUserMessageId);
            }
        } catch (error) {
            console.error("[App] Failed to send message:", error);
            this.ui.showAlert('Failed to send message', 'danger');
            this.messages.addMessageToDOM('system', `Error: connection issue or server error.`);
            this.ui.showThinking(false);
        }
    }

    async handleNonStreamingMessage(messageContent, tempUserMessageId) {
        console.log("[App] Handling non-streaming message");
        
        const data = await this.api.sendMessage(messageContent);
        this.ui.showThinking(false);

        if (data.error) {
            this.ui.showAlert(data.error, 'danger');
            this.messages.addMessageToDOM('system', `Error: ${data.error}`);
        } else {
            // Update user message ID if changed
            if (data.parent_id && tempUserMessageId !== data.parent_id) {
                this.updateMessageId(tempUserMessageId, data.parent_id);
            }

            // Add assistant response
            this.messages.addMessageToDOM('assistant', data.response, data.message_id, {
                model: data.model,
                parent_id: data.parent_id,
                token_usage: data.token_usage
            });

            this.conversations.addMessageToTree(data.message_id, {
                role: 'assistant',
                content: data.response,
                model: data.model,
                parent_id: data.parent_id,
                token_usage: data.token_usage
            });

            if (data.conversation_id) {
                this.conversations.setCurrentConversation(data.conversation_id, this.conversations.conversationName);
            }

            this.updateAllSiblingIndicators();
        }
    }

    async handleStreamingMessage(messageContent, tempUserMessageId) {
        console.log("[App] Handling streaming message");
        
        let fullResponseText = "";
        let tempAssistantMessageId = `msg-assistant-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        
        this.ui.showThinking(false);
        this.messages.addMessageToDOM('assistant', '...', tempAssistantMessageId, {
            parent_id: tempUserMessageId,
            model: "Streaming..."
        });

        try {
            for await (const eventData of this.api.streamMessage(messageContent)) {
                if (eventData.error) {
                    this.messages.updateMessageInDOM(tempAssistantMessageId, `Error: ${eventData.error}`);
                    this.ui.showAlert(eventData.error, 'danger');
                    return;
                }

                if (eventData.chunk) {
                    fullResponseText += eventData.chunk;
                    this.messages.updateMessageInDOM(tempAssistantMessageId, fullResponseText);
                }

                if (eventData.done) {
                    // Update assistant message ID
                    if (eventData.message_id) {
                        this.updateMessageId(tempAssistantMessageId, eventData.message_id);
                        this.conversations.updateMessageInTree(eventData.message_id, {
                            content: fullResponseText,
                            model: eventData.model,
                            token_usage: eventData.token_usage,
                            parent_id: eventData.parent_id
                        });
                    }

                    // Update user message ID if needed
                    if (eventData.parent_id && tempUserMessageId !== eventData.parent_id) {
                        this.updateMessageId(tempUserMessageId, eventData.parent_id);
                    }

                    // Update model display
                    this.messages.updateMessageInDOM(eventData.message_id, fullResponseText, {
                        model: eventData.model
                    });

                    if (eventData.conversation_id) {
                        this.conversations.setCurrentConversation(eventData.conversation_id, this.conversations.conversationName);
                    }

                    this.updateAllSiblingIndicators();
                    return;
                }
            }
        } catch (error) {
            console.error("[App] Streaming error:", error);
            this.messages.updateMessageInDOM(tempAssistantMessageId, `Error: ${error.message}`);
            this.ui.showAlert('Streaming error', 'danger');
        }
    }

    updateMessageId(oldId, newId) {
        console.log(`[App] Updating message ID from ${oldId} to ${newId}`);
        
        // Update DOM element
        const element = this.messages.messageElements[oldId];
        if (element) {
            element.id = newId;
            this.messages.messageElements[newId] = element;
            delete this.messages.messageElements[oldId];
        }

        // Update message tree
        if (this.conversations.messageTree[oldId]) {
            this.conversations.messageTree[newId] = this.conversations.messageTree[oldId];
            this.conversations.messageTree[newId].id = newId;
            delete this.conversations.messageTree[oldId];
        }
    }

    async handleCommand(command) {
        console.log(`[App] Handling command: ${command}`);
        return await this.commands.handleCommand(command);
    }

    // ============ UI Display Methods ============

    displayConversationsList(conversations) {
        console.log(`[App] Displaying ${conversations.length} conversations`);
        
        const listElement = document.getElementById('conversationsList');
        listElement.innerHTML = '';
        
        if (!Array.isArray(conversations)) return;

        conversations.forEach(conv => {
            const li = document.createElement('li');
            li.className = 'nav-item conversation-list-item position-relative';
            
            const createdDate = conv.created_at 
                ? new Date(conv.created_at).toLocaleDateString([], { 
                    year: '2-digit', 
                    month: 'numeric', 
                    day: 'numeric' 
                  }) 
                : 'N/A';
            
            const convIdForActions = conv.conversation_id || conv.filename;
            const convIdForLoading = conv.filename || conv.conversation_id || conv.title;

            li.innerHTML = `
                <a class="nav-link d-flex justify-content-between align-items-center" 
                   href="#" 
                   onclick="app.loadConversationByName('${convIdForLoading.replace(/'/g, "\\'")}')">
                    <div style="max-width: calc(100% - 30px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        <strong id="conv-title-${convIdForActions}">${conv.title}</strong><br>
                        <small class="text-muted">${conv.message_count || 0} messages • ${createdDate}</small>
                    </div>
                </a>
                <div class="conversation-actions-menu position-absolute end-0 me-1" 
                     style="top: 50%; transform: translateY(-50%); z-index: 10;">
                    <button class="btn btn-sm btn-light py-0 px-1 three-dots-btn" 
                            aria-expanded="false" 
                            aria-controls="dropdown-${convIdForActions}" 
                            title="Conversation actions">
                        <i class="bi bi-three-dots-vertical"></i>
                    </button>
                    <div class="dropdown-menu conversation-item-dropdown p-1" 
                         id="dropdown-${convIdForActions}" 
                         style="min-width: auto;">
                        <button class="dropdown-item d-flex align-items-center py-1 px-2" 
                                type="button" 
                                onclick="app.promptDuplicateConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')">
                            <i class="bi bi-copy me-2"></i>Duplicate
                        </button>
                        <button class="dropdown-item d-flex align-items-center py-1 px-2" 
                                type="button" 
                                onclick="app.promptRenameConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')">
                            <i class="bi bi-pencil-square me-2"></i>Rename
                        </button>
                        <div class="dropdown-divider my-1"></div>
                        <button class="dropdown-item d-flex align-items-center py-1 px-2 text-danger" 
                                type="button" 
                                onclick="app.confirmDeleteConversation('${convIdForActions}', '${conv.title.replace(/'/g, "\\'")}')">
                            <i class="bi bi-trash me-2"></i>Delete
                        </button>
                    </div>
                </div>`;
            
            listElement.appendChild(li);
        });
    }

    displayModelsList(models) {
        console.log(`[App] Displaying ${models.length} models`);
        
        const tbody = document.getElementById('modelsList');
        tbody.innerHTML = '';
        
        if (!Array.isArray(models)) return;

        models.forEach(model => {
            const tr = document.createElement('tr');
            const outputLimit = this.settings.modelCapabilities[model.name]?.output_token_limit || 'N/A';
            const inputLimit = this.settings.modelCapabilities[model.name]?.input_token_limit || 'N/A';
            
            tr.innerHTML = `
                <td><code>${model.name}</code></td>
                <td>${model.display_name}</td>
                <td>${inputLimit}</td>
                <td>${outputLimit}</td>
                <td>
                    <button class="btn btn-sm btn-primary" 
                            onclick="app.selectModel('${model.name}')">
                        Select
                    </button>
                </td>`;
            
            tbody.appendChild(tr);
        });
    }

    updateAllSiblingIndicators() {
        console.log("[App] Updating all sibling indicators");
        
        const allSiblings = this.conversations.getAllSiblingsForIndicators(this.messages.messageElements);
        
        allSiblings.forEach(({ parentId, siblings }) => {
            this.messages.updateSiblingIndicators(parentId, siblings, this.conversations.messageTree);
        });
    }

    // ============ Action Methods (called from HTML) ============

    async loadConversationByName(name) {
        console.log(`[App] Loading conversation by name: ${name}`);
        await this.commands.loadConversation(name);
    }

    async saveConversation() {
        console.log("[App] Saving conversation");
        await this.commands.saveConversation();
    }

    async selectModel(modelName) {
        console.log(`[App] Selecting model: ${modelName}`);
        await this.commands.selectModel(modelName);
        this.ui.hideModelSelectorModal();
    }

    async retryMessage(messageId) {
        console.log(`[App] Retrying message: ${messageId}`);
        this.ui.showThinking(true);
        
        try {
            const data = await this.api.retryMessage(messageId);
            if (data.error) {
                this.ui.showAlert(data.error, 'danger');
                return;
            }

            // Update conversation state
            this.conversations.setCurrentConversation(data.conversation_id, data.conversation_name);
            
            if (data.system_instruction !== undefined) {
                this.conversations.updateSystemInstruction(data.system_instruction);
                this.ui.updateSystemInstructionDisplay(data.system_instruction);
                this.settings.updateModelSettingsForm(
                    data.params || this.settings.appSettings.params,
                    data.streaming !== undefined ? data.streaming : this.settings.streamingEnabled,
                    this.conversations.currentSystemInstruction
                );
            }

            if (data.full_message_tree) {
                this.conversations.updateMessageTree(data.full_message_tree);
            }

            if (data.history && Array.isArray(data.history)) {
                this.messages.rebuildChatFromHistory(data.history);
            }

            this.ui.showAlert('Generated new response', 'success');
            this.updateAllSiblingIndicators();
        } catch (error) {
            console.error("[App] Failed to retry message:", error);
            this.ui.showAlert('Failed to retry message', 'danger');
        } finally {
            this.ui.showThinking(false);
        }
    }

    async navigateSibling(messageId, direction) {
        console.log(`[App] Navigating sibling: ${messageId}, direction: ${direction}`);
        this.ui.showThinking(true);
        
        try {
            const data = await this.api.navigateSibling(messageId, direction);
            
            if (data.error) {
                this.ui.showAlert(data.error, 'danger');
                return;
            }

            // Update conversation state
            this.conversations.setCurrentConversation(data.conversation_id, data.conversation_name);
            
            if (data.system_instruction !== undefined) {
                this.conversations.updateSystemInstruction(data.system_instruction);
                this.ui.updateSystemInstructionDisplay(data.system_instruction);
                this.settings.updateModelSettingsForm(
                    data.params || this.settings.appSettings.params,
                    data.streaming !== undefined ? data.streaming : this.settings.streamingEnabled,
                    this.conversations.currentSystemInstruction
                );
            }

            if (data.full_message_tree) {
                this.conversations.updateMessageTree(data.full_message_tree);
            }

            if (data.history && Array.isArray(data.history)) {
                this.messages.rebuildChatFromHistory(data.history);
            } else {
                this.messages.clearChatDisplay();
                this.ui.showAlert('Navigation resulted in empty history.', 'warning');
            }

            if (direction !== 'none' && data.total_siblings > 1) {
                this.ui.showAlert(`Switched to response ${data.sibling_index + 1} of ${data.total_siblings}`, 'info');
            }

            this.updateAllSiblingIndicators();
        } catch (error) {
            console.error("[App] Failed to navigate sibling:", error);
            this.ui.showAlert('Failed to navigate to sibling', 'danger');
        } finally {
            this.ui.showThinking(false);
        }
    }

    // ============ Modal Actions ============

    showNewConversationModal() {
        console.log("[App] Showing new conversation modal");
        this.ui.showNewConversationModal();
    }

    async createNewConversation() {
        console.log("[App] Creating new conversation from modal");
        const title = this.ui.getNewConversationTitle();
        
        try {
            await this.commands.newConversation(title);
            this.ui.hideNewConversationModal();
        } catch (error) {
            this.ui.showAlert('Failed to create new conversation', 'danger');
        }
    }

    showModelSelector() {
        console.log("[App] Showing model selector");
        this.ui.showModelSelectorModal();
    }

    showAppSettingsModal() {
        console.log("[App] Showing app settings modal");
        this.ui.showAppSettingsModal(this.settings.appSettings);
        this.updatePreview();
    }

    saveAppSettings() {
        console.log("[App] Saving app settings");
        
        if (this.settings.updateSettingsFromModal()) {
            this.settings.applySettings();
            this.messages.reRenderAllMessagesVisuals(this.settings.appSettings);
            this.ui.showAlert('App settings saved', 'success');
            this.ui.hideAppSettingsModal();
        } else {
            this.ui.showAlert('Failed to save app settings', 'danger');
        }
    }

    resetAppSettings() {
        console.log("[App] Resetting app settings");
        
        if (this.ui.confirmAction('Reset all app settings to defaults? This will clear your locally stored preferences.')) {
            this.settings.resetSettings();
            this.messages.reRenderAllMessagesVisuals(this.settings.appSettings);
            this.ui.showAppSettingsModal(this.settings.appSettings);
            this.ui.showAlert('App settings reset to defaults', 'info');
        }
    }

    updatePreview() {
        console.log("[App] Updating settings preview");
        
        // Get current form values
        const previewSettings = {
            theme: document.querySelector('input[name="theme"]:checked')?.value || 'light',
            fontSize: parseInt(document.getElementById('fontSize')?.value || 16),
            fontFamily: document.getElementById('fontFamily')?.value || 'system-ui',
            showTimestamps: document.getElementById('showTimestamps')?.checked || false,
            showAvatars: document.getElementById('showAvatars')?.checked || false,
            showMetadataIcons: document.getElementById('showMetadataIcons')?.checked || false,
            enableAnimations: document.getElementById('enableAnimations')?.checked || false,
            compactMode: document.getElementById('compactMode')?.checked || false,
            codeTheme: document.getElementById('codeTheme')?.value || 'github-dark',
            showLineNumbers: document.getElementById('showLineNumbers')?.checked || false
        };
        
        this.ui.updateSettingsPreview(previewSettings);
    }

    showSystemInstructionModal() {
        console.log("[App] Showing system instruction modal");
        this.ui.showSystemInstructionModal(this.conversations.currentSystemInstruction);
    }

    async saveSystemInstructionFromModal() {
        console.log("[App] Saving system instruction from modal");
        
        const newInstruction = this.ui.getSystemInstructionFromModal();
        
        if (!this.conversations.currentConversationId) {
            this.ui.showAlert(
                "No active conversation to save system instruction to. Will apply to next new conversation if default is not overridden by loaded conversation.", 
                "warning"
            );
            this.conversations.updateSystemInstruction(newInstruction);
            this.ui.updateSystemInstructionDisplay(newInstruction);
            this.ui.hideSystemInstructionModal();
            return;
        }

        try {
            const data = await this.api.updateSystemInstruction(
                this.conversations.currentConversationId, 
                newInstruction
            );
            
            if (data.success) {
                this.conversations.updateSystemInstruction(data.system_instruction);
                this.ui.updateSystemInstructionDisplay(data.system_instruction);
                this.ui.showAlert('System instruction saved for current conversation.', 'success');
                this.ui.hideSystemInstructionModal();
            } else {
                this.ui.showAlert(data.error || 'Failed to save system instruction.', 'danger');
            }
        } catch (error) {
            console.error("[App] Error saving system instruction:", error);
            this.ui.showAlert('Error saving system instruction.', 'danger');
        }
    }

    toggleModelSettingsSidebar() {
        console.log("[App] Toggling model settings sidebar");
        this.ui.toggleModelSettingsSidebar();
    }

    async saveModelSettingsFromSidebar() {
        console.log("[App] Saving model settings from sidebar");
        
        const params = this.settings.getCurrentFormParams();
        const streaming = this.settings.getCurrentStreamingPreference();

        try {
            const data = await this.api.updateSettings({ params, streaming });
            
            if (data.success) {
                this.settings.streamingEnabled = data.streaming;
                this.ui.updateStreamingStatus(data.streaming);
                this.settings.updateModelSettingsForm(data.params, data.streaming, this.conversations.currentSystemInstruction);
                this.ui.showAlert('Session settings (params, streaming) applied', 'success');
            } else {
                this.ui.showAlert(data.error || 'Failed to apply session settings', 'danger');
            }
        } catch (error) {
            console.error("[App] Failed to save model settings:", error);
            this.ui.showAlert('Failed to apply session settings', 'danger');
        }
    }

    // ============ Conversation Actions ============

    async promptDuplicateConversation(conversationId, currentTitle) {
        console.log(`[App] Prompting to duplicate conversation: ${conversationId}`);
        
        const newTitle = this.ui.promptUser(
            `Enter a title for the duplicated conversation (current: "${currentTitle}"):`, 
            `Copy of ${currentTitle}`
        );
        
        if (newTitle && newTitle.trim() !== '') {
            await this.apiDuplicateConversation(conversationId, newTitle.trim());
        }
    }

    async apiDuplicateConversation(conversationId, newTitle) {
        console.log(`[App] Duplicating conversation: ${conversationId}`);
        this.ui.showThinking(true);
        
        try {
            const data = await this.api.duplicateConversation(conversationId, newTitle);
            
            if (data.success) {
                this.ui.showAlert(`Conversation duplicated as "${data.new_title}"`, 'success');
                await this.loadConversations();
            } else {
                this.ui.showAlert(data.error || 'Failed to duplicate conversation', 'danger');
            }
        } catch (error) {
            console.error("[App] Failed to duplicate:", error);
            this.ui.showAlert('Client error duplicating conversation', 'danger');
        } finally {
            this.ui.showThinking(false);
        }
    }

    async promptRenameConversation(conversationId, currentTitle) {
        console.log(`[App] Prompting to rename conversation: ${conversationId}`);
        
        const newTitle = this.ui.promptUser(
            `Enter the new title for "${currentTitle}":`, 
            currentTitle
        );
        
        if (newTitle !== null && newTitle.trim() !== '' && newTitle.trim() !== currentTitle) {
            await this.apiRenameConversation(conversationId, newTitle.trim());
        }
    }

    async apiRenameConversation(conversationId, newTitle) {
        console.log(`[App] Renaming conversation: ${conversationId}`);
        this.ui.showThinking(true);
        
        try {
            const data = await this.api.renameConversation(conversationId, newTitle);
            
            if (data.success) {
                this.ui.showAlert(`Conversation renamed to "${data.new_title}"`, 'success');
                await this.loadConversations();
                
                // Update current conversation name if it's the active one
                if (this.conversations.currentConversationId === data.conversation_id) {
                    this.conversations.setCurrentConversation(data.conversation_id, data.new_title);
                    
                    // Update in message tree
                    if (this.conversations.messageTree?.metadata) {
                        this.conversations.messageTree.metadata.title = data.new_title;
                    }
                }
            } else {
                this.ui.showAlert(data.error || 'Failed to rename conversation', 'danger');
            }
        } catch (error) {
            console.error("[App] Failed to rename:", error);
            this.ui.showAlert('Client error renaming conversation', 'danger');
        } finally {
            this.ui.showThinking(false);
        }
    }

    async confirmDeleteConversation(conversationId, title) {
        console.log(`[App] Confirming deletion of conversation: ${conversationId}`);
        
        if (this.ui.confirmAction(`Are you sure you want to delete the conversation "${title}"? This cannot be undone.`)) {
            await this.apiDeleteConversation(conversationId);
        }
    }

    async apiDeleteConversation(conversationId) {
        console.log(`[App] Deleting conversation: ${conversationId}`);
        this.ui.showThinking(true);
        
        try {
            const data = await this.api.deleteConversation(conversationId);
            
            if (data.success) {
                this.ui.showAlert(`Conversation deleted`, 'success');
                await this.loadConversations();
                
                // Clear current conversation if it was deleted
                if (this.conversations.currentConversationId === data.deleted_conversation_id) {
                    this.conversations.clearConversation();
                    this.messages.clearChatDisplay();
                    this.conversations.currentSystemInstruction = this.settings.appSettings.defaultSystemInstruction || "You are a helpful assistant.";
                    this.ui.updateSystemInstructionDisplay(this.conversations.currentSystemInstruction);
                    this.settings.updateModelSettingsForm(
                        this.settings.appSettings.params || {},
                        this.settings.streamingEnabled,
                        this.conversations.currentSystemInstruction
                    );
                }
            } else {
                this.ui.showAlert(data.error || 'Failed to delete conversation', 'danger');
            }
        } catch (error) {
            console.error("[App] Failed to delete:", error);
            this.ui.showAlert('Client error deleting conversation', 'danger');
        } finally {
            this.ui.showThinking(false);
        }
    }

    showMessageMetadata(messageId) {
        console.log(`[App] Showing metadata for message: ${messageId}`);
        
        const messageData = this.conversations.findMessage(messageId);
        if (!messageData) {
            this.ui.showAlert('Could not find metadata for this message.', 'warning');
            return;
        }
        
        this.ui.showMessageMetadataModal(messageData);
    }

    async copyMetadataToClipboard() {
        console.log("[App] Copying metadata to clipboard");
        
        const metadataContentEl = document.getElementById('messageMetadataContent');
        if (metadataContentEl) {
            await this.ui.copyToClipboard(metadataContentEl.textContent);
        }
    }

    // ============ Shortcuts ============

    async toggleStreaming() {
        console.log("[App] Toggling streaming");
        await this.commands.toggleStreaming();
    }

    showHistory() {
        console.log("[App] Showing history");
        this.commands.showHistory();
    }
}

// Initialize the application
console.log("[App] Loading CannonAI Application");
const app = new CannonAIApp();
