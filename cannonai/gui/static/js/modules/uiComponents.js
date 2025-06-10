/**
 * CannonAI UI Components Module
 * Handles UI elements, modals, alerts, and visual feedback
 */

export class UIComponents {
    constructor() {
        console.log("[UIComponents] Initializing");
        
        this.modals = {};
        this.rightSidebarOpen = true;
        this.mainContentDefaultClasses = ['col-md-9', 'col-lg-10'];
        this.mainContentRightSidebarOpenClasses = ['col-md-6', 'col-lg-8'];
        
        // Initialize Bootstrap modals after DOM ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initModals());
        } else {
            this.initModals();
        }
    }

    /**
     * Initialize Bootstrap modals
     */
    initModals() {
        console.log("[UIComponents] Initializing Bootstrap modals");
        
        // Get modal elements
        const modalElements = {
            newConversation: document.getElementById('newConversationModal'),
            modelSelector: document.getElementById('modelSelectorModal'),
            appSettings: document.getElementById('appSettingsModal'),
            messageMetadata: document.getElementById('messageMetadataModal'),
            systemInstruction: document.getElementById('systemInstructionModal')
        };
        
        // Create Bootstrap modal instances
        for (const [name, element] of Object.entries(modalElements)) {
            if (element) {
                this.modals[name] = new bootstrap.Modal(element);
                console.log(`[UIComponents] Modal initialized: ${name}`);
            } else {
                console.warn(`[UIComponents] Modal element not found: ${name}`);
            }
        }
    }

    /**
     * Show alert message
     */
    showAlert(message, type = 'info') {
        console.log(`[UIComponents] Showing alert: ${type} - ${message}`);
        
        const alertContainer = document.getElementById('alertContainer');
        if (!alertContainer) {
            console.warn("[UIComponents] Alert container not found");
            return;
        }
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show m-0 mb-2`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        alertContainer.appendChild(alertDiv);
        
        // Create Bootstrap alert instance
        const bsAlert = new bootstrap.Alert(alertDiv);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (bootstrap.Alert.getInstance(alertDiv)) {
                bsAlert.close();
            } else if (alertDiv.parentElement) {
                alertDiv.remove();
            }
        }, 5000);
    }

    /**
     * Show/hide thinking indicator
     */
    showThinking(show) {
        console.log(`[UIComponents] Thinking indicator: ${show ? 'show' : 'hide'}`);
        const indicator = document.getElementById('thinkingIndicator');
        if (indicator) {
            indicator.classList.toggle('d-none', !show);
        }
    }

    /**
     * Update connection status display
     */
    updateConnectionStatus(connected = true) {
        console.log(`[UIComponents] Connection status: ${connected ? 'connected' : 'disconnected'}`);
        const statusEl = document.getElementById('connectionStatus');
        if (statusEl) {
            statusEl.innerHTML = `
                <i class="bi bi-circle-fill ${connected ? 'text-success pulsate-connection' : 'text-danger'}"></i> 
                ${connected ? 'Connected' : 'Disconnected'}
            `;
        }
    }

    /**
     * Update streaming status display
     */
    updateStreamingStatus(enabled) {
        console.log(`[UIComponents] Streaming status: ${enabled ? 'ON' : 'OFF'}`);
        const streamingModeEl = document.getElementById('streamingMode');
        if (streamingModeEl) {
            streamingModeEl.textContent = enabled ? 'ON' : 'OFF';
        }
    }

    /**
     * Update system instruction display
     */
    updateSystemInstructionDisplay(instruction) {
        console.log("[UIComponents] Updating system instruction display");
        const displayEl = document.getElementById('systemInstructionDisplay');
        if (displayEl) {
            const shortInstruction = instruction && instruction.length > 20 
                ? instruction.substring(0, 20) + "..." 
                : (instruction || "Default");
            displayEl.textContent = shortInstruction;
            
            const parentStatusEl = document.getElementById('systemInstructionStatus');
            if (parentStatusEl) {
                parentStatusEl.title = instruction || "Default System Instruction";
            }
        }
    }

    /**
     * Toggle model settings sidebar
     */
    toggleModelSettingsSidebar() {
        console.log("[UIComponents] Toggling model settings sidebar");
        
        const sidebar = document.getElementById('modelSettingsSidebar');
        const mainContent = document.getElementById('mainContent');
        
        if (!sidebar || !mainContent) {
            console.warn("[UIComponents] Sidebar or main content element not found");
            return;
        }

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
        
        console.log(`[UIComponents] Sidebar is now ${this.rightSidebarOpen ? 'open' : 'closed'}`);
    }

    /**
     * Show new conversation modal
     */
    showNewConversationModal() {
        console.log("[UIComponents] Showing new conversation modal");
        const titleInput = document.getElementById('conversationTitleInput');
        if (titleInput) {
            titleInput.value = '';
        }
        this.modals.newConversation?.show();
    }

    /**
     * Hide new conversation modal
     */
    hideNewConversationModal() {
        console.log("[UIComponents] Hiding new conversation modal");
        this.modals.newConversation?.hide();
    }

    /**
     * Show model selector modal
     */
    showModelSelectorModal() {
        console.log("[UIComponents] Showing model selector modal");
        this.modals.modelSelector?.show();
    }

    /**
     * Hide model selector modal
     */
    hideModelSelectorModal() {
        console.log("[UIComponents] Hiding model selector modal");
        this.modals.modelSelector?.hide();
    }

    /**
     * Show app settings modal
     */
    showAppSettingsModal(settings) {
        console.log("[UIComponents] Showing app settings modal");
        
        // Populate form with current settings
        if (settings) {
            document.getElementById(`theme${settings.theme.charAt(0).toUpperCase() + settings.theme.slice(1)}`)?.setAttribute('checked', 'checked');
            document.getElementById('fontSize').value = settings.fontSize;
            document.getElementById('fontSizeValue').textContent = settings.fontSize;
            document.getElementById('fontFamily').value = settings.fontFamily;
            document.getElementById('showTimestamps').checked = settings.showTimestamps;
            document.getElementById('showAvatars').checked = settings.showAvatars;
            document.getElementById('showMetadataIcons').checked = settings.showMetadataIcons;
            document.getElementById('enableAnimations').checked = settings.enableAnimations;
            document.getElementById('compactMode').checked = settings.compactMode;
            document.getElementById('codeTheme').value = settings.codeTheme;
            document.getElementById('showLineNumbers').checked = settings.showLineNumbers;
        }
        
        this.modals.appSettings?.show();
    }

    /**
     * Hide app settings modal
     */
    hideAppSettingsModal() {
        console.log("[UIComponents] Hiding app settings modal");
        this.modals.appSettings?.hide();
    }

    /**
     * Show system instruction modal
     */
    showSystemInstructionModal(currentInstruction) {
        console.log("[UIComponents] Showing system instruction modal");
        const modalInput = document.getElementById('systemInstructionModalInput');
        if (modalInput) {
            modalInput.value = currentInstruction || '';
        }
        
        if (this.modals.systemInstruction) {
            this.modals.systemInstruction.show();
        } else {
            this.showAlert("System instruction modal not available.", "warning");
        }
    }

    /**
     * Hide system instruction modal
     */
    hideSystemInstructionModal() {
        console.log("[UIComponents] Hiding system instruction modal");
        this.modals.systemInstruction?.hide();
    }

    /**
     * Show message metadata modal
     */
    showMessageMetadataModal(metadata) {
        console.log("[UIComponents] Showing message metadata modal");
        const metadataContentEl = document.getElementById('messageMetadataContent');
        if (metadataContentEl) {
            const displayData = { ...metadata };
            metadataContentEl.textContent = JSON.stringify(displayData, null, 2);
            
            // Apply syntax highlighting if hljs is available
            if (window.hljs) {
                window.hljs.highlightElement(metadataContentEl);
            }
        }
        this.modals.messageMetadata?.show();
    }

    /**
     * Initialize textarea auto-resize
     */
    initTextareaAutoResize() {
        console.log("[UIComponents] Initializing textarea auto-resize");
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

    /**
     * Update settings preview in modal
     */
    updateSettingsPreview(settings) {
        console.log("[UIComponents] Updating settings preview");
        const preview = document.getElementById('settingsPreview');
        if (!preview) return;

        // Update font settings
        preview.style.fontSize = `${settings.fontSize}px`;
        preview.style.fontFamily = settings.fontFamily;

        // Update visibility settings
        const previewAvatarContainer = preview.querySelector('#previewAvatarContainer');
        if (previewAvatarContainer) {
            previewAvatarContainer.style.display = settings.showAvatars ? 'flex' : 'none';
        }

        const previewMetadataIcon = preview.querySelector('.btn-message-info-icon');
        if (previewMetadataIcon) {
            previewMetadataIcon.style.display = settings.showMetadataIcons ? 'inline-block' : 'none';
        }

        const previewTimestamp = preview.querySelector('#previewTimestamp');
        if (previewTimestamp) {
            previewTimestamp.style.display = settings.showTimestamps ? 'inline' : 'none';
        }

        // Update theme
        let previewThemeClass = `theme-${settings.theme}`;
        if (settings.theme === 'auto') {
            previewThemeClass = window.matchMedia('(prefers-color-scheme: dark)').matches 
                ? 'theme-dark' 
                : 'theme-light';
        }
        preview.className = `preview-area border rounded p-3 ${previewThemeClass}`;

        // Update code highlighting
        const codeBlock = preview.querySelector('pre code');
        if (codeBlock && window.hljs) {
            window.hljs.highlightElement(codeBlock);
            
            // Handle line numbers
            const showPreviewLineNumbers = settings.showLineNumbers;
            if (showPreviewLineNumbers) {
                if (!codeBlock.classList.contains('line-numbers-active-preview')) {
                    const lines = codeBlock.innerHTML.split('\n');
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') 
                        ? lines.slice(0, -1) 
                        : lines;
                    codeBlock.innerHTML = effectiveLines
                        .map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`)
                        .join('\n');
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

    /**
     * Get new conversation title from modal
     */
    getNewConversationTitle() {
        const titleInput = document.getElementById('conversationTitleInput');
        return titleInput ? titleInput.value.trim() : '';
    }

    /**
     * Get system instruction from modal
     */
    getSystemInstructionFromModal() {
        const input = document.getElementById('systemInstructionModalInput');
        return input ? input.value : '';
    }

    /**
     * Prompt for user input
     */
    promptUser(message, defaultValue = '') {
        console.log(`[UIComponents] Prompting user: ${message}`);
        return prompt(message, defaultValue);
    }

    /**
     * Confirm action with user
     */
    confirmAction(message) {
        console.log(`[UIComponents] Confirming action: ${message}`);
        return confirm(message);
    }

    /**
     * Copy text to clipboard
     */
    async copyToClipboard(text) {
        console.log("[UIComponents] Copying to clipboard");
        
        try {
            if (navigator.clipboard) {
                await navigator.clipboard.writeText(text);
                this.showAlert('Copied to clipboard!', 'success');
                return true;
            } else {
                // Fallback for older browsers
                const textarea = document.createElement('textarea');
                textarea.value = text;
                document.body.appendChild(textarea);
                textarea.select();
                
                try {
                    document.execCommand('copy');
                    this.showAlert('Copied to clipboard! (fallback)', 'success');
                    return true;
                } catch (err) {
                    console.error('Fallback copy failed:', err);
                    this.showAlert('Failed to copy to clipboard.', 'danger');
                    return false;
                } finally {
                    document.body.removeChild(textarea);
                }
            }
        } catch (err) {
            console.error('Failed to copy:', err);
            this.showAlert('Failed to copy to clipboard.', 'danger');
            return false;
        }
    }
}
