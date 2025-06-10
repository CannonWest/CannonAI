/**
 * CannonAI Message Renderer Module
 * Handles message display, formatting, and DOM manipulation
 */

export class MessageRenderer {
    constructor() {
        console.log("[MessageRenderer] Initializing");
        this.messageElements = {};
        this.hljs = window.hljs;
        this.marked = window.marked;
        
        // Configure marked.js
        this._configureMarked();
    }

    _configureMarked() {
        console.log("[MessageRenderer] Configuring marked.js");
        this.marked.setOptions({
            highlight: (code, lang) => {
                const language = this.hljs.getLanguage(lang) ? lang : 'plaintext';
                try {
                    return this.hljs.highlight(code, { language, ignoreIllegals: true }).value;
                } catch (e) {
                    console.error('[MessageRenderer] Highlight.js error:', e);
                    return this.hljs.highlightAuto(code).value;
                }
            },
            breaks: true,
            gfm: true
        });
    }

    /**
     * Add a message to the DOM
     */
    addMessageToDOM(role, content, messageId, metadata = {}) {
        console.log(`[MessageRenderer] Adding ${role} message: ${messageId}`);
        
        const uniqueMessageId = messageId || `msg-${role}-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
        const contentString = (typeof content === 'string') ? content : JSON.stringify(content);

        const chatMessages = document.getElementById('chatMessages');
        
        // Remove empty state if present
        const emptyState = chatMessages.querySelector('.text-center.text-muted.py-5');
        if (emptyState) emptyState.remove();

        // Check if message already exists
        let messageRow = this.messageElements[uniqueMessageId];
        if (!messageRow) {
            messageRow = document.createElement('div');
            messageRow.className = `message-row message-${role}`;
            messageRow.id = uniqueMessageId;
            chatMessages.appendChild(messageRow);
            this.messageElements[uniqueMessageId] = messageRow;
        }

        // Determine icon and label based on role
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

        // Format timestamp
        const messageTimestamp = metadata.timestamp || new Date().toISOString();
        const displayTime = new Date(messageTimestamp).toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit' 
        });

        // Build header HTML
        let headerHTML = `<strong>${roleLabel}</strong>`;
        
        if (role === 'assistant' && metadata.model) {
            headerHTML += ` <span class="badge bg-secondary text-dark me-2">${metadata.model.split('/').pop()}</span>`;
        }
        
        // Add info button
        headerHTML += `
            <button class="btn btn-sm btn-message-info-icon p-0 me-2" 
                    onclick="window.app.showMessageMetadata('${uniqueMessageId}')" 
                    title="View Message Metadata">
                <i class="bi bi-info-circle"></i>
            </button>`;
        
        headerHTML += ` <span class="text-muted ms-auto message-timestamp-display">${displayTime}</span>`;

        // Build actions HTML for assistant messages
        let actionsHTML = '';
        if (role === 'assistant') {
            actionsHTML = `
                <div class="message-actions">
                    <button class="btn btn-sm btn-retry" 
                            onclick="window.app.retryMessage('${uniqueMessageId}')" 
                            title="Generate another response">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <button class="btn btn-sm btn-prev-sibling" 
                            onclick="window.app.navigateSibling('${uniqueMessageId}', 'prev')" 
                            title="Previous response" 
                            style="display: none;">
                        <i class="bi bi-chevron-left"></i>
                    </button>
                    <button class="btn btn-sm btn-next-sibling" 
                            onclick="window.app.navigateSibling('${uniqueMessageId}', 'next')" 
                            title="Next response" 
                            style="display: none;">
                        <i class="bi bi-chevron-right"></i>
                    </button>
                </div>`;
        }

        // Build complete message HTML
        messageRow.innerHTML = `
            <div class="message-icon me-2 ms-2">
                <i class="bi ${iconClass} fs-4"></i>
            </div>
            <div class="message-body">
                <div class="message-header d-flex align-items-center mb-1">
                    ${headerHTML}
                </div>
                <div class="message-content p-2 rounded shadow-sm">
                    ${this.formatMessageContent(contentString)}
                </div>
                ${actionsHTML}
            </div>`;

        // Add branch indicator for assistant messages
        if (role === 'assistant') {
            this._addBranchIndicator(messageRow);
        }

        // Apply code highlighting
        this.applyCodeHighlighting(messageRow);
        
        // Scroll to bottom
        this.scrollToBottom();
        
        console.log(`[MessageRenderer] Message ${uniqueMessageId} added to DOM`);
        return uniqueMessageId;
    }

    /**
     * Update an existing message in the DOM
     */
    updateMessageInDOM(messageId, newContent, newMetadata = {}) {
        console.log(`[MessageRenderer] Updating message: ${messageId}`);
        
        const messageDiv = this.messageElements[messageId] || document.getElementById(messageId);
        if (!messageDiv) {
            console.warn(`[MessageRenderer] Message element ${messageId} not found`);
            return;
        }

        // Update content
        const contentDiv = messageDiv.querySelector('.message-content');
        if (contentDiv) {
            contentDiv.innerHTML = this.formatMessageContent(newContent);
            this.applyCodeHighlighting(contentDiv);
        }

        // Update model badge if provided
        if (newMetadata.model) {
            const modelBadge = messageDiv.querySelector('.message-header .badge.bg-secondary');
            if (modelBadge) {
                modelBadge.textContent = newMetadata.model.split('/').pop();
            }
        }

        this.scrollToBottom();
    }

    /**
     * Format message content with markdown
     */
    formatMessageContent(content) {
        if (typeof content !== 'string') {
            content = String(content);
        }
        
        try {
            console.log("[MessageRenderer] Parsing markdown content");
            return this.marked.parse(content);
        } catch (error) {
            console.error('[MessageRenderer] Markdown parsing failed:', error);
            // Fallback to basic HTML escaping
            const escaped = content
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/\n/g, '<br>');
            return escaped;
        }
    }

    /**
     * Apply syntax highlighting to code blocks
     */
    applyCodeHighlighting(containerElement, showLineNumbers = false) {
        console.log("[MessageRenderer] Applying code highlighting");
        
        containerElement.querySelectorAll('pre code').forEach(block => {
            this.hljs.highlightElement(block);
            
            if (showLineNumbers) {
                if (!block.classList.contains('line-numbers-active')) {
                    const lines = block.innerHTML.split('\n');
                    const effectiveLines = (lines.length > 1 && lines[lines.length - 1] === '') 
                        ? lines.slice(0, -1) 
                        : lines;
                    
                    block.innerHTML = effectiveLines
                        .map((line, i) => `<span class="line-number">${String(i + 1).padStart(3, ' ')}</span>${line}`)
                        .join('\n');
                    
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

    /**
     * Clear all messages from display
     */
    clearChatDisplay() {
        console.log("[MessageRenderer] Clearing chat display");
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = `
            <div class="text-center text-muted py-5">
                <i class="bi bi-chat-dots display-1"></i>
                <p>Start a new conversation or load an existing one.</p>
            </div>`;
        this.messageElements = {};
    }

    /**
     * Rebuild chat from history array
     */
    rebuildChatFromHistory(history) {
        console.log(`[MessageRenderer] Rebuilding chat from history (${history?.length || 0} messages)`);
        
        const chatMessages = document.getElementById('chatMessages');
        chatMessages.innerHTML = '';
        this.messageElements = {};

        if (!Array.isArray(history) || history.length === 0) {
            this.clearChatDisplay();
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
    }

    /**
     * Add branch indicator to assistant message
     */
    _addBranchIndicator(messageRow) {
        const headerElement = messageRow.querySelector('.message-header');
        if (!headerElement) return;

        const indicatorSpan = document.createElement('span');
        indicatorSpan.className = 'branch-indicator badge bg-info ms-2';
        indicatorSpan.style.display = 'none';
        
        const indicatorText = document.createElement('span');
        indicatorText.className = 'branch-indicator-text';
        indicatorSpan.appendChild(indicatorText);

        // Find insertion point
        const modelBadge = headerElement.querySelector('.badge.bg-secondary');
        const infoIconBtn = headerElement.querySelector('.btn-message-info-icon');

        if (modelBadge) {
            modelBadge.insertAdjacentElement('afterend', indicatorSpan);
        } else if (infoIconBtn) {
            infoIconBtn.insertAdjacentElement('afterend', indicatorSpan);
        } else {
            headerElement.querySelector('strong')?.insertAdjacentElement('afterend', indicatorSpan);
        }
    }

    /**
     * Update sibling indicators for messages with multiple responses
     */
    updateSiblingIndicators(parentId, siblings, messageTree) {
        console.log(`[MessageRenderer] Updating sibling indicators for parent: ${parentId}`);
        
        if (!siblings || siblings.length === 0) return;

        siblings.forEach((siblingId, index) => {
            const element = this.messageElements[siblingId] || document.getElementById(siblingId);
            if (!element) return;

            // Update branch indicator
            const indicatorSpan = element.querySelector('.branch-indicator');
            const indicatorTextEl = element.querySelector('.branch-indicator-text');

            if (indicatorSpan && indicatorTextEl) {
                if (siblings.length > 1) {
                    indicatorTextEl.textContent = `${index + 1} / ${siblings.length}`;
                    indicatorSpan.style.display = 'inline-block';
                } else {
                    indicatorSpan.style.display = 'none';
                }
            }

            // Update navigation buttons
            const prevBtn = element.querySelector('.btn-prev-sibling');
            const nextBtn = element.querySelector('.btn-next-sibling');
            
            if (prevBtn && nextBtn) {
                const showNav = siblings.length > 1;
                prevBtn.style.display = showNav ? 'inline-flex' : 'none';
                nextBtn.style.display = showNav ? 'inline-flex' : 'none';
                prevBtn.disabled = (index === 0);
                nextBtn.disabled = (index === siblings.length - 1);
            }
        });
    }

    /**
     * Scroll chat to bottom
     */
    scrollToBottom() {
        const chatContainer = document.getElementById('chatMessages');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }

    /**
     * Re-render all messages with updated settings
     */
    reRenderAllMessagesVisuals(settings) {
        console.log("[MessageRenderer] Re-rendering all messages with new settings");
        
        document.querySelectorAll('.message-row').forEach(messageEl => {
            // Update avatar visibility
            const avatarEl = messageEl.querySelector('.message-icon');
            if (avatarEl) {
                avatarEl.style.display = settings.showAvatars ? 'flex' : 'none';
            }

            // Update timestamp visibility
            const timestampEl = messageEl.querySelector('.message-timestamp-display');
            if (timestampEl) {
                timestampEl.style.display = settings.showTimestamps ? 'inline' : 'none';
            }

            // Update metadata icon visibility
            const metadataIconEl = messageEl.querySelector('.btn-message-info-icon');
            if (metadataIconEl) {
                metadataIconEl.style.display = settings.showMetadataIcons ? 'inline-block' : 'none';
            }

            // Re-apply code highlighting with line numbers setting
            this.applyCodeHighlighting(messageEl, settings.showLineNumbers);
        });
    }
}
