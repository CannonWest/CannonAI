/**
 * CannonAI Command Handler Module
 * Processes slash commands and executes appropriate actions
 */

export class CommandHandler {
    constructor(apiClient, conversationManager, messageRenderer, uiComponents) {
        console.log("[CommandHandler] Initializing");
        
        this.api = apiClient;
        this.conversations = conversationManager;
        this.messages = messageRenderer;
        this.ui = uiComponents;
        
        // Define available commands
        this.commands = {
            '/help': this.showHelp.bind(this),
            '/new': this.newConversation.bind(this),
            '/load': this.loadConversation.bind(this),
            '/save': this.saveConversation.bind(this),
            '/list': this.listConversations.bind(this),
            '/model': this.selectModel.bind(this),
            '/stream': this.toggleStreaming.bind(this),
            '/clear': this.clearScreen.bind(this),
            '/history': this.showHistory.bind(this),
            '/version': this.showVersion.bind(this)
        };
    }

    /**
     * Handle a command string
     */
    async handleCommand(command) {
        console.log(`[CommandHandler] Processing command: ${command}`);
        
        // Extract command and arguments
        const parts = command.trim().split(' ');
        const cmd = parts[0].toLowerCase();
        const args = parts.slice(1).join(' ');
        
        // Check for direct command match
        if (this.commands[cmd]) {
            console.log(`[CommandHandler] Executing direct command: ${cmd}`);
            return await this.commands[cmd](args);
        }
        
        // Check for commands with arguments
        for (const [cmdKey, handler] of Object.entries(this.commands)) {
            if (cmd.startsWith(cmdKey)) {
                console.log(`[CommandHandler] Executing command with args: ${cmdKey}`);
                return await handler(args || cmd.substring(cmdKey.length).trim());
            }
        }
        
        // If no local handler, send to server
        console.log("[CommandHandler] No local handler, sending to server");
        return await this.executeServerCommand(command);
    }

    /**
     * Execute command on server
     */
    async executeServerCommand(command) {
        console.log(`[CommandHandler] Executing server command: ${command}`);
        
        try {
            const response = await this.api.executeCommand(command);
            
            if (response.error) {
                this.ui.showAlert(response.error, 'danger');
                return false;
            }
            
            // Handle response based on success
            if (response.success) {
                await this.handleSuccessfulCommand(response, command);
            } else if (response.message) {
                this.messages.addMessageToDOM('system', response.message);
            }
            
            return response.success;
            
        } catch (error) {
            console.error("[CommandHandler] Command execution failed:", error);
            this.ui.showAlert('Command failed', 'danger');
            return false;
        }
    }

    /**
     * Handle successful command response
     */
    async handleSuccessfulCommand(data, originalCommand) {
        console.log("[CommandHandler] Handling successful command response");
        
        // Update conversation ID if provided
        if (data.conversation_id) {
            this.conversations.setCurrentConversation(
                data.conversation_id, 
                data.conversation_name || this.conversations.conversationName
            );
        }
        
        // Update message tree if provided
        if (data.full_message_tree) {
            this.conversations.updateMessageTree(data.full_message_tree);
        }
        
        // Rebuild chat display if history provided
        if (data.history && Array.isArray(data.history)) {
            this.messages.rebuildChatFromHistory(data.history);
        } else if (originalCommand.startsWith('/new')) {
            this.messages.clearChatDisplay();
            this.conversations.clearConversation();
        }
        
        // Update model if changed
        if (data.model && window.app?.settings) {
            window.app.settings.setCurrentModel(data.model);
        }
        
        // Update system instruction if provided
        if (data.system_instruction !== undefined) {
            this.conversations.updateSystemInstruction(data.system_instruction);
            this.ui.updateSystemInstructionDisplay(data.system_instruction);
        }
        
        // Update settings if provided
        if (data.params && window.app?.settings) {
            window.app.settings.updateModelSettingsForm(
                data.params,
                data.streaming !== undefined ? data.streaming : window.app.settings.streamingEnabled,
                this.conversations.currentSystemInstruction
            );
        }
        
        // Update streaming status if changed
        if (data.streaming !== undefined && window.app?.settings) {
            window.app.settings.streamingEnabled = data.streaming;
            this.ui.updateStreamingStatus(data.streaming);
        }
        
        // Show success message if provided
        if (data.message && data.success) {
            this.ui.showAlert(data.message, 'info');
        }
        
        // Update sibling indicators
        if (window.app?.updateAllSiblingIndicators) {
            window.app.updateAllSiblingIndicators();
        }
        
        // Reload conversations list for relevant commands
        const reloadCommands = ['/new', '/load', '/list', '/save', '/delete', '/rename', '/duplicate'];
        if (reloadCommands.some(cmd => originalCommand.startsWith(cmd))) {
            if (window.app?.loadConversations) {
                await window.app.loadConversations();
            }
        }
    }

    /**
     * Show help information
     */
    async showHelp() {
        console.log("[CommandHandler] Showing help");
        
        const helpContent = `
            <h5>Available Commands (type in chat):</h5>
            <ul>
                <li><code>/new [title]</code> - Start a new conversation.</li>
                <li><code>/load [name/id]</code> - Load a conversation.</li>
                <li><code>/save</code> - Save current conversation.</li>
                <li><code>/list</code> - Refresh and show saved conversations.</li>
                <li><code>/model [name]</code> - Change AI model (for current provider). Lists if no name.</li>
                <li><code>/stream</code> - Toggle client's session streaming preference.</li>
                <li><code>/clear</code> - Clear the screen.</li>
                <li><code>/history</code> - Show conversation history.</li>
                <li><code>/version</code> - Show version information.</li>
                <li><code>/help</code> - Show this help.</li>
            </ul>
            <p><small>Generation parameters and system instructions are managed via UI elements in the header and right sidebar.</small></p>
        `;
        
        this.messages.addMessageToDOM('system', helpContent, `help-${Date.now()}`);
        return true;
    }

    /**
     * Create new conversation
     */
    async newConversation(title = '') {
        console.log(`[CommandHandler] Creating new conversation with title: ${title}`);
        return await this.executeServerCommand(`/new ${title}`);
    }

    /**
     * Load conversation
     */
    async loadConversation(identifier) {
        console.log(`[CommandHandler] Loading conversation: ${identifier}`);
        
        if (!identifier) {
            this.ui.showAlert('Please specify a conversation to load', 'warning');
            return false;
        }
        
        return await this.executeServerCommand(`/load ${identifier}`);
    }

    /**
     * Save current conversation
     */
    async saveConversation() {
        console.log("[CommandHandler] Saving conversation");
        return await this.executeServerCommand('/save');
    }

    /**
     * List conversations
     */
    async listConversations() {
        console.log("[CommandHandler] Listing conversations");
        
        // Refresh the conversations list
        if (window.app?.loadConversations) {
            await window.app.loadConversations();
        }
        
        return await this.executeServerCommand('/list');
    }

    /**
     * Select or list models
     */
    async selectModel(modelName) {
        console.log(`[CommandHandler] Model command with arg: ${modelName}`);
        
        if (!modelName) {
            // Show model selector modal
            this.ui.showModelSelectorModal();
            return true;
        }
        
        return await this.executeServerCommand(`/model ${modelName}`);
    }

    /**
     * Toggle streaming mode
     */
    async toggleStreaming() {
        console.log("[CommandHandler] Toggling streaming mode");
        return await this.executeServerCommand('/stream');
    }

    /**
     * Clear the screen
     */
    async clearScreen() {
        console.log("[CommandHandler] Clearing screen");
        this.messages.clearChatDisplay();
        this.ui.showAlert('Screen cleared', 'info');
        return true;
    }

    /**
     * Show conversation history
     */
    async showHistory() {
        console.log("[CommandHandler] Showing history");
        this.ui.showAlert('Full conversation history for the active branch is displayed.', 'info');
        return true;
    }

    /**
     * Show version information
     */
    async showVersion() {
        console.log("[CommandHandler] Showing version");
        
        const versionInfo = `
            <h5>CannonAI Version Information</h5>
            <ul>
                <li><strong>Frontend:</strong> v1.0.0 (Modular)</li>
                <li><strong>API Version:</strong> v2.3.0</li>
                <li><strong>Last Updated:</strong> ${new Date().toLocaleDateString()}</li>
            </ul>
        `;
        
        this.messages.addMessageToDOM('system', versionInfo, `version-${Date.now()}`);
        return true;
    }
}
