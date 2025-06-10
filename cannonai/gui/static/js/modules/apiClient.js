/**
 * CannonAI API Client Module
 * Handles all API communication with the Flask backend
 */

export class APIClient {
    constructor(apiBase) {
        console.log("[APIClient] Initializing with base URL:", apiBase);
        this.apiBase = apiBase || window.location.origin;
    }

    // ============ Connection & Status ============

    async getStatus() {
        console.log("[APIClient] Getting connection status");
        try {
            const response = await fetch(`${this.apiBase}/api/status`);
            const data = await response.json();
            console.log("[APIClient] Status response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to get status:", error);
            return { connected: false, error: error.message };
        }
    }

    async getModels() {
        console.log("[APIClient] Fetching available models");
        try {
            const response = await fetch(`${this.apiBase}/api/models`);
            const data = await response.json();
            console.log("[APIClient] Models response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to fetch models:", error);
            return { error: error.message, models: [] };
        }
    }

    // ============ Message Handling ============

    async sendMessage(message, attachments = null) {
        console.log("[APIClient] Sending non-streaming message:", message?.substring(0, 50) + "...");
        try {
            const response = await fetch(`${this.apiBase}/api/send`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, attachments })
            });
            const data = await response.json();
            console.log("[APIClient] Send response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to send message:", error);
            throw error;
        }
    }

    async* streamMessage(message, attachments = null) {
        console.log("[APIClient] Starting streaming message:", message?.substring(0, 50) + "...");
        try {
            const response = await fetch(`${this.apiBase}/api/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, attachments })
            });

            if (!response.ok || !response.body) {
                throw new Error(`Streaming request failed: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                let boundary = buffer.indexOf("\n\n");

                while (boundary !== -1) {
                    const line = buffer.substring(0, boundary);
                    buffer = buffer.substring(boundary + 2);
                    boundary = buffer.indexOf("\n\n");

                    if (line.startsWith("data: ")) {
                        try {
                            const eventData = JSON.parse(line.substring(6));
                            console.log("[APIClient] Stream event:", eventData);
                            yield eventData;
                            
                            if (eventData.done || eventData.error) {
                                console.log("[APIClient] Stream complete");
                                return;
                            }
                        } catch (e) {
                            console.warn("[APIClient] Failed to parse SSE event:", line, e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error("[APIClient] Streaming error:", error);
            yield { error: error.message };
        }
    }

    // ============ Conversation Management ============

    async getConversations() {
        console.log("[APIClient] Fetching conversations list");
        try {
            const response = await fetch(`${this.apiBase}/api/conversations`);
            const data = await response.json();
            console.log("[APIClient] Conversations count:", data.conversations?.length || 0);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to fetch conversations:", error);
            return { error: error.message, conversations: [] };
        }
    }

    async newConversation(title = '') {
        console.log("[APIClient] Creating new conversation with title:", title);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/new`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title })
            });
            const data = await response.json();
            console.log("[APIClient] New conversation response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to create conversation:", error);
            throw error;
        }
    }

    async loadConversation(identifier) {
        console.log("[APIClient] Loading conversation:", identifier);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/load/${identifier}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            console.log("[APIClient] Load conversation response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to load conversation:", error);
            throw error;
        }
    }

    async saveConversation() {
        console.log("[APIClient] Saving current conversation");
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await response.json();
            console.log("[APIClient] Save response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to save conversation:", error);
            throw error;
        }
    }

    async duplicateConversation(conversationId, newTitle) {
        console.log("[APIClient] Duplicating conversation:", conversationId, "with title:", newTitle);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/duplicate/${conversationId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            console.log("[APIClient] Duplicate response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to duplicate conversation:", error);
            throw error;
        }
    }

    async renameConversation(conversationId, newTitle) {
        console.log("[APIClient] Renaming conversation:", conversationId, "to:", newTitle);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/rename/${conversationId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_title: newTitle })
            });
            const data = await response.json();
            console.log("[APIClient] Rename response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to rename conversation:", error);
            throw error;
        }
    }

    async deleteConversation(conversationId) {
        console.log("[APIClient] Deleting conversation:", conversationId);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/delete/${conversationId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            console.log("[APIClient] Delete response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to delete conversation:", error);
            throw error;
        }
    }

    // ============ Settings & Configuration ============

    async getSettings() {
        console.log("[APIClient] Fetching settings");
        try {
            const response = await fetch(`${this.apiBase}/api/settings`);
            const data = await response.json();
            console.log("[APIClient] Settings response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to fetch settings:", error);
            throw error;
        }
    }

    async updateSettings(settings) {
        console.log("[APIClient] Updating settings:", settings);
        try {
            const response = await fetch(`${this.apiBase}/api/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            const data = await response.json();
            console.log("[APIClient] Update settings response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to update settings:", error);
            throw error;
        }
    }

    async updateSystemInstruction(conversationId, systemInstruction) {
        console.log("[APIClient] Updating system instruction for conversation:", conversationId);
        try {
            const response = await fetch(`${this.apiBase}/api/conversation/${conversationId}/system_instruction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ system_instruction: systemInstruction })
            });
            const data = await response.json();
            console.log("[APIClient] Update system instruction response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to update system instruction:", error);
            throw error;
        }
    }

    // ============ Command & Control ============

    async executeCommand(command) {
        console.log("[APIClient] Executing command:", command);
        try {
            const response = await fetch(`${this.apiBase}/api/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command })
            });
            const data = await response.json();
            console.log("[APIClient] Command response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to execute command:", error);
            throw error;
        }
    }

    // ============ Message Navigation ============

    async retryMessage(messageId) {
        console.log("[APIClient] Retrying message:", messageId);
        try {
            const response = await fetch(`${this.apiBase}/api/retry/${messageId}`, {
                method: 'POST'
            });
            const data = await response.json();
            console.log("[APIClient] Retry response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to retry message:", error);
            throw error;
        }
    }

    async navigateSibling(messageId, direction) {
        console.log("[APIClient] Navigating sibling:", messageId, "direction:", direction);
        try {
            const response = await fetch(`${this.apiBase}/api/navigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_id: messageId, direction })
            });
            const data = await response.json();
            console.log("[APIClient] Navigate response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to navigate sibling:", error);
            throw error;
        }
    }

    async getMessageInfo(messageId) {
        console.log("[APIClient] Getting message info:", messageId);
        try {
            const response = await fetch(`${this.apiBase}/api/message/${messageId}`);
            const data = await response.json();
            console.log("[APIClient] Message info response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to get message info:", error);
            throw error;
        }
    }

    async getConversationTree() {
        console.log("[APIClient] Getting conversation tree");
        try {
            const response = await fetch(`${this.apiBase}/api/tree`);
            const data = await response.json();
            console.log("[APIClient] Tree response:", data);
            return data;
        } catch (error) {
            console.error("[APIClient] Failed to get conversation tree:", error);
            throw error;
        }
    }
}
