/**
 * CannonAI Conversation Manager Module
 * Handles conversation state, message tree structure, and navigation
 */

export class ConversationManager {
    constructor() {
        console.log("[ConversationManager] Initializing");
        this.currentConversationId = null;
        this.conversationName = "New Conversation";
        this.messageTree = {};
        this.currentSystemInstruction = "You are a helpful assistant.";
    }

    /**
     * Set the current conversation
     */
    setCurrentConversation(conversationId, conversationName) {
        console.log(`[ConversationManager] Setting current conversation: ${conversationId} - ${conversationName}`);
        this.currentConversationId = conversationId;
        this.conversationName = conversationName || "New Conversation";
        
        // Update UI
        const convNameEl = document.getElementById('conversationName');
        if (convNameEl) {
            convNameEl.textContent = this.conversationName;
        }
    }

    /**
     * Clear conversation state
     */
    clearConversation() {
        console.log("[ConversationManager] Clearing conversation state");
        this.currentConversationId = null;
        this.conversationName = "New Conversation";
        this.messageTree = {};
        
        const convNameEl = document.getElementById('conversationName');
        if (convNameEl) {
            convNameEl.textContent = this.conversationName;
        }
    }

    /**
     * Update message tree from server data
     */
    updateMessageTree(messageTree) {
        console.log("[ConversationManager] Updating message tree");
        this.messageTree = messageTree || {};
        this._rebuildMessageTreeRelationships();
    }

    /**
     * Add or update a message in the tree
     */
    addMessageToTree(messageId, messageData) {
        console.log(`[ConversationManager] Adding message to tree: ${messageId}`);
        
        if (!this.messageTree[messageId]) {
            this.messageTree[messageId] = {
                id: messageId,
                role: messageData.role,
                content: messageData.content,
                parent_id: messageData.parent_id || null,
                children: [],
                model: messageData.model,
                timestamp: messageData.timestamp || new Date().toISOString(),
                token_usage: messageData.token_usage || {},
                attachments: messageData.attachments,
                ...(messageData.params && { params: messageData.params }),
                ...(messageData.branch_id && { branch_id: messageData.branch_id }),
            };
        } else {
            // Update existing message
            Object.assign(this.messageTree[messageId], messageData);
        }

        // Update parent's children array
        if (messageData.parent_id && this.messageTree[messageData.parent_id]) {
            const parentNode = this.messageTree[messageData.parent_id];
            if (!Array.isArray(parentNode.children)) {
                parentNode.children = [];
            }
            if (!parentNode.children.includes(messageId)) {
                parentNode.children.push(messageId);
            }
        }
    }

    /**
     * Update a message in the tree
     */
    updateMessageInTree(messageId, updates) {
        console.log(`[ConversationManager] Updating message in tree: ${messageId}`);
        
        if (this.messageTree[messageId]) {
            Object.assign(this.messageTree[messageId], updates);
        }
    }

    /**
     * Get the last message ID from the active branch
     */
    getLastMessageIdFromActiveBranch() {
        console.log("[ConversationManager] Getting last message ID from active branch");
        
        const chatMessagesContainer = document.getElementById('chatMessages');
        const messageElements = chatMessagesContainer.querySelectorAll('.message-row');
        
        if (messageElements.length > 0) {
            return messageElements[messageElements.length - 1].id;
        }
        
        return null;
    }

    /**
     * Rebuild message tree relationships
     */
    _rebuildMessageTreeRelationships() {
        console.log("[ConversationManager] Rebuilding message tree relationships");
        
        if (Object.keys(this.messageTree).length === 0) return;

        // Initialize children arrays
        for (const msgId in this.messageTree) {
            if (!this.messageTree[msgId].children || !Array.isArray(this.messageTree[msgId].children)) {
                this.messageTree[msgId].children = [];
            }
        }

        // Rebuild parent-child relationships
        for (const msgId in this.messageTree) {
            const messageNode = this.messageTree[msgId];
            if (messageNode.parent_id && this.messageTree[messageNode.parent_id]) {
                const parentNode = this.messageTree[messageNode.parent_id];
                if (!Array.isArray(parentNode.children)) {
                    parentNode.children = [];
                }
                if (!parentNode.children.includes(msgId)) {
                    parentNode.children.push(msgId);
                }
            }
        }

        console.log(`[ConversationManager] Rebuilt relationships for ${Object.keys(this.messageTree).length} messages`);
    }

    /**
     * Get siblings of a message
     */
    getMessageSiblings(messageId) {
        console.log(`[ConversationManager] Getting siblings for message: ${messageId}`);
        
        const message = this.messageTree[messageId];
        if (!message || !message.parent_id) {
            return { siblings: [], currentIndex: -1 };
        }

        const parent = this.messageTree[message.parent_id];
        if (!parent || !parent.children) {
            return { siblings: [], currentIndex: -1 };
        }

        const siblings = parent.children;
        const currentIndex = siblings.indexOf(messageId);

        return { siblings, currentIndex };
    }

    /**
     * Get all siblings that need indicators
     */
    getAllSiblingsForIndicators(messageElements) {
        console.log("[ConversationManager] Getting all siblings for indicators");
        
        const parentIdsToCheck = new Set();

        // Check displayed messages
        Object.values(messageElements).forEach(domEl => {
            const msgNode = this.messageTree[domEl.id];
            if (msgNode && msgNode.parent_id && this.messageTree[msgNode.parent_id]) {
                parentIdsToCheck.add(msgNode.parent_id);
            }
        });

        // Check all messages with children
        for (const msgId in this.messageTree) {
            const msgNode = this.messageTree[msgId];
            if (msgNode.children && msgNode.children.length > 0) {
                parentIdsToCheck.add(msgId);
            }
        }

        const result = [];
        parentIdsToCheck.forEach(parentId => {
            const parent = this.messageTree[parentId];
            if (parent && parent.children && parent.children.length > 0) {
                result.push({
                    parentId,
                    siblings: parent.children
                });
            }
        });

        return result;
    }

    /**
     * Update system instruction
     */
    updateSystemInstruction(instruction) {
        console.log("[ConversationManager] Updating system instruction");
        this.currentSystemInstruction = instruction || "You are a helpful assistant.";
        
        // Update tree metadata if it exists
        if (this.messageTree && this.messageTree.metadata) {
            this.messageTree.metadata.system_instruction = this.currentSystemInstruction;
        }
    }

    /**
     * Get conversation metadata
     */
    getConversationMetadata() {
        const metadata = {
            conversation_id: this.currentConversationId,
            conversation_name: this.conversationName,
            system_instruction: this.currentSystemInstruction,
            message_count: Object.keys(this.messageTree).length,
            has_messages: Object.keys(this.messageTree).length > 0
        };

        // Include tree metadata if available
        if (this.messageTree && this.messageTree.metadata) {
            Object.assign(metadata, this.messageTree.metadata);
        }

        return metadata;
    }

    /**
     * Find message by ID
     */
    findMessage(messageId) {
        return this.messageTree[messageId] || null;
    }

    /**
     * Get conversation history as array
     */
    getHistoryArray() {
        console.log("[ConversationManager] Building history array from tree");
        
        const history = [];
        const visited = new Set();

        // Simple depth-first traversal starting from messages without parents
        const traverse = (messageId) => {
            if (visited.has(messageId)) return;
            visited.add(messageId);

            const message = this.messageTree[messageId];
            if (message) {
                history.push({
                    id: message.id,
                    role: message.role || message.type,
                    content: message.content,
                    model: message.model,
                    timestamp: message.timestamp,
                    parent_id: message.parent_id,
                    token_usage: message.token_usage,
                    attachments: message.attachments
                });

                // Traverse children
                if (message.children && message.children.length > 0) {
                    message.children.forEach(childId => traverse(childId));
                }
            }
        };

        // Find root messages (no parent)
        Object.keys(this.messageTree).forEach(messageId => {
            const message = this.messageTree[messageId];
            if (!message.parent_id) {
                traverse(messageId);
            }
        });

        return history;
    }
}
