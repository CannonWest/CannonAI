/**
 * CannonAI Settings Manager Module
 * Handles application settings, themes, and user preferences
 */

export class SettingsManager {
    constructor() {
        console.log("[SettingsManager] Initializing");
        
        // Model capabilities storage
        this.modelCapabilities = {};
        this.DEFAULT_MODEL_MAX_TOKENS = 8192;
        this.MIN_OUTPUT_TOKENS = 128;
        this.TOKEN_SLIDER_STEP = 128;
        
        // Current session settings
        this.streamingEnabled = false;
        this.currentModelName = null;
        
        // Default app settings
        this.defaultSettings = {
            theme: 'light',
            fontSize: 16,
            fontFamily: 'system-ui',
            showTimestamps: true,
            showAvatars: true,
            enableAnimations: true,
            compactMode: false,
            codeTheme: 'github-dark',
            showLineNumbers: true,
            showMetadataIcons: true,
            defaultSystemInstruction: "You are a helpful assistant.",
            params: {
                temperature: 0.7,
                max_output_tokens: 800,
                top_p: 0.95,
                top_k: 40
            }
        };
        
        // Load saved settings
        this.appSettings = this.loadSettings();
        
        // Debounce timer for parameter changes
        this.paramChangeTimeout = null;
    }

    /**
     * Load settings from localStorage
     */
    loadSettings() {
        console.log("[SettingsManager] Loading settings from localStorage");
        try {
            const saved = localStorage.getItem('cannonAIAppSettings');
            const loaded = saved ? JSON.parse(saved) : {};
            
            // Merge with defaults
            const settings = {
                ...this.defaultSettings,
                ...loaded,
                params: {
                    ...this.defaultSettings.params,
                    ...(loaded.params || {})
                }
            };
            
            console.log("[SettingsManager] Settings loaded:", settings);
            return settings;
        } catch (e) {
            console.error("[SettingsManager] Error loading settings:", e);
            return { ...this.defaultSettings };
        }
    }

    /**
     * Save settings to localStorage
     */
    saveSettings() {
        console.log("[SettingsManager] Saving settings to localStorage");
        try {
            localStorage.setItem('cannonAIAppSettings', JSON.stringify(this.appSettings));
            console.log("[SettingsManager] Settings saved successfully");
            return true;
        } catch (e) {
            console.error("[SettingsManager] Error saving settings:", e);
            return false;
        }
    }

    /**
     * Apply all settings to the UI
     */
    applySettings() {
        console.log("[SettingsManager] Applying all settings");
        this.applyTheme(this.appSettings.theme);
        this.applyFontSettings();
        this.applyVisibilitySettings();
        this.updateCodeThemeLink(this.appSettings.codeTheme);
    }

    /**
     * Apply theme
     */
    applyTheme(themeName) {
        console.log(`[SettingsManager] Applying theme: ${themeName}`);
        
        document.body.classList.remove('theme-light', 'theme-dark');
        
        let effectiveTheme = themeName;
        if (themeName === 'auto') {
            effectiveTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            console.log(`[SettingsManager] Auto theme detected: ${effectiveTheme}`);
        }
        
        document.body.classList.add(`theme-${effectiveTheme}`);
        
        // Update code theme if set to default
        let codeThemeToApply = this.appSettings.codeTheme;
        if (this.appSettings.codeTheme === 'default') {
            codeThemeToApply = effectiveTheme === 'dark' ? 'github-dark' : 'github';
        }
        this.updateCodeThemeLink(codeThemeToApply, false);
    }

    /**
     * Apply font settings
     */
    applyFontSettings() {
        console.log("[SettingsManager] Applying font settings");
        document.documentElement.style.setProperty('--chat-font-size', `${this.appSettings.fontSize}px`);
        document.documentElement.style.setProperty('--chat-font-family', this.appSettings.fontFamily);
    }

    /**
     * Apply visibility settings
     */
    applyVisibilitySettings() {
        console.log("[SettingsManager] Applying visibility settings");
        document.body.classList.toggle('hide-timestamps', !this.appSettings.showTimestamps);
        document.body.classList.toggle('hide-avatars', !this.appSettings.showAvatars);
        document.body.classList.toggle('disable-animations', !this.appSettings.enableAnimations);
        document.body.classList.toggle('compact-mode', this.appSettings.compactMode);
        document.body.classList.toggle('hide-metadata-icons', !this.appSettings.showMetadataIcons);
    }

    /**
     * Update code syntax highlighting theme
     */
    updateCodeThemeLink(themeName, saveSetting = true) {
        console.log(`[SettingsManager] Updating code theme: ${themeName}`);
        
        let link = document.querySelector('link[id="highlightjs-theme"]');
        if (!link) {
            link = document.createElement('link');
            link.id = 'highlightjs-theme';
            link.rel = 'stylesheet';
            document.head.appendChild(link);
        }
        
        link.href = `https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${themeName}.min.css`;
        
        if (saveSetting) {
            this.appSettings.codeTheme = themeName;
        }
        
        // Re-highlight existing code blocks
        document.querySelectorAll('pre code').forEach(block => {
            const parentPre = block.closest('pre');
            if (parentPre && window.hljs) {
                const tempContent = block.textContent;
                block.className = `language-${block.className.match(/language-(\S+)/)?.[1] || 'plaintext'} hljs`;
                block.innerHTML = tempContent;
                window.hljs.highlightElement(block);
            }
        });
    }

    /**
     * Update model capabilities
     */
    updateModelCapabilities(models) {
        console.log("[SettingsManager] Updating model capabilities");
        this.modelCapabilities = {};
        
        if (Array.isArray(models)) {
            models.forEach(model => {
                this.modelCapabilities[model.name] = {
                    output_token_limit: model.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS,
                    input_token_limit: model.input_token_limit || 0
                };
            });
        }
        
        console.log("[SettingsManager] Model capabilities updated:", this.modelCapabilities);
    }

    /**
     * Get model max tokens
     */
    getModelMaxTokens(modelName) {
        return this.modelCapabilities[modelName]?.output_token_limit || this.DEFAULT_MODEL_MAX_TOKENS;
    }

    /**
     * Update model settings form
     */
    updateModelSettingsForm(params, streamingStatus, systemInstruction) {
        console.log("[SettingsManager] Updating model settings form");
        
        if (!params) params = {};

        // Temperature
        const tempSlider = document.getElementById('temperatureSlider');
        const tempInput = document.getElementById('temperatureInput');
        if (tempSlider && tempInput) {
            const tempValue = parseFloat(params.temperature !== undefined ? params.temperature : 0.7);
            tempSlider.value = tempValue;
            tempInput.value = tempValue.toFixed(2);
        }

        // Max tokens
        const maxTokensSlider = document.getElementById('maxTokensSlider');
        const maxTokensInput = document.getElementById('maxTokensInput');
        if (maxTokensSlider && maxTokensInput) {
            const currentModelMax = this.getModelMaxTokens(this.currentModelName);
            maxTokensSlider.min = this.MIN_OUTPUT_TOKENS;
            maxTokensInput.min = this.MIN_OUTPUT_TOKENS;
            maxTokensSlider.max = currentModelMax;
            maxTokensInput.max = currentModelMax;
            maxTokensSlider.step = this.TOKEN_SLIDER_STEP;
            maxTokensInput.step = this.TOKEN_SLIDER_STEP;

            let currentSetValue = parseInt(params.max_output_tokens !== undefined ? params.max_output_tokens : 800);
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax;
            if (currentSetValue < this.MIN_OUTPUT_TOKENS) currentSetValue = this.MIN_OUTPUT_TOKENS;
            
            // Round to nearest step
            currentSetValue = Math.round((currentSetValue - this.MIN_OUTPUT_TOKENS) / this.TOKEN_SLIDER_STEP) * this.TOKEN_SLIDER_STEP + this.MIN_OUTPUT_TOKENS;
            if (currentSetValue > currentModelMax) currentSetValue = currentModelMax;

            maxTokensSlider.value = currentSetValue;
            maxTokensInput.value = currentSetValue;
        }

        // Top-p
        const topPSlider = document.getElementById('topPSlider');
        const topPInput = document.getElementById('topPInput');
        if (topPSlider && topPInput) {
            const topPValue = parseFloat(params.top_p !== undefined ? params.top_p : 0.95);
            topPSlider.value = topPValue;
            topPInput.value = topPValue.toFixed(2);
        }

        // Top-k
        const topKInput = document.getElementById('topKInput');
        if (topKInput) {
            topKInput.value = parseInt(params.top_k !== undefined ? params.top_k : 40);
        }

        // Streaming toggle
        const streamingToggle = document.getElementById('streamingToggleRightSidebar');
        if (streamingToggle) {
            streamingToggle.checked = streamingStatus;
        }
        
        this.streamingEnabled = streamingStatus;
    }

    /**
     * Get current form parameters
     */
    getCurrentFormParams() {
        console.log("[SettingsManager] Getting current form parameters");
        
        return {
            temperature: parseFloat(document.getElementById('temperatureInput')?.value || 0.7),
            max_output_tokens: parseInt(document.getElementById('maxTokensInput')?.value || 800),
            top_p: parseFloat(document.getElementById('topPInput')?.value || 0.95),
            top_k: parseInt(document.getElementById('topKInput')?.value || 40)
        };
    }

    /**
     * Get current streaming preference
     */
    getCurrentStreamingPreference() {
        return document.getElementById('streamingToggleRightSidebar')?.checked || false;
    }

    /**
     * Reset settings to defaults
     */
    resetSettings() {
        console.log("[SettingsManager] Resetting settings to defaults");
        localStorage.removeItem('cannonAIAppSettings');
        this.appSettings = this.loadSettings();
        this.applySettings();
    }

    /**
     * Update settings from modal form
     */
    updateSettingsFromModal() {
        console.log("[SettingsManager] Updating settings from modal");
        
        this.appSettings = {
            theme: document.querySelector('input[name="theme"]:checked')?.value || 'light',
            fontSize: parseInt(document.getElementById('fontSize')?.value || 16),
            fontFamily: document.getElementById('fontFamily')?.value || 'system-ui',
            showTimestamps: document.getElementById('showTimestamps')?.checked || false,
            showAvatars: document.getElementById('showAvatars')?.checked || false,
            showMetadataIcons: document.getElementById('showMetadataIcons')?.checked || false,
            enableAnimations: document.getElementById('enableAnimations')?.checked || false,
            compactMode: document.getElementById('compactMode')?.checked || false,
            codeTheme: document.getElementById('codeTheme')?.value || 'github-dark',
            showLineNumbers: document.getElementById('showLineNumbers')?.checked || false,
            defaultSystemInstruction: this.appSettings.defaultSystemInstruction,
            params: this.appSettings.params
        };
        
        return this.saveSettings();
    }

    /**
     * Set current model
     */
    setCurrentModel(modelName) {
        console.log(`[SettingsManager] Setting current model: ${modelName}`);
        this.currentModelName = modelName;
        
        // Update display
        const modelEl = document.getElementById('currentModelDisplay');
        if (modelEl) {
            modelEl.textContent = modelName ? modelName.split('/').pop() : 'N/A';
        }
    }
}
