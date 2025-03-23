// src/views/qml/components/SettingsDialog.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs

Dialog {
    id: settingsDialog
    title: "API Settings"
    width: 600
    height: 700
    modal: true

    // Properties to store current settings
    property var currentSettings: ({})

    // Properties to store model information
    property var mainModels: []
    property var modelSnapshots: []
    property var currentModelInfo: {}
    property bool isCurrentModelReasoning: false
    property var reasoningEfforts: ["low", "medium", "high"]
    property var responseFormats: ["text", "json_object"]

    // Signals
    signal settingsSaved(var settings)

    // Custom background and styling
    background: Rectangle {
        color: backgroundColor
        radius: 8
        border.color: accentColor
        border.width: 1
    }

    // Main content
    contentItem: ScrollView {
        id: scrollView
        anchors.fill: parent
        clip: true

        ColumnLayout {
            width: scrollView.width
            spacing: 16

            // API Configuration
            GroupBox {
                title: "API Configuration"
                Layout.fillWidth: true

                background: Rectangle {
                    color: Qt.rgba(0.27, 0.28, 0.35, 0.5)
                    radius: 4
                    border.color: accentColor
                    border.width: 1
                }

                label: Label {
                    text: parent.title
                    color: foregroundColor
                    font.bold: true
                    padding: 4
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    Label {
                        text: "API Key:"
                        color: foregroundColor
                    }

                    TextField {
                        id: apiKeyField
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        placeholderText: "Enter your OpenAI API key"
                        text: currentSettings.api_key || ""

                        background: Rectangle {
                            color: highlightColor
                            radius: 4
                        }

                        color: foregroundColor
                    }

                    Label {
                        text: "API Base URL:"
                        color: foregroundColor
                    }

                    TextField {
                        id: apiBaseField
                        Layout.fillWidth: true
                        placeholderText: "https://api.openai.com/v1"
                        text: currentSettings.api_base || ""

                        background: Rectangle {
                            color: highlightColor
                            radius: 4
                        }

                        color: foregroundColor
                    }

                    Label {
                        text: "API Type:"
                        color: foregroundColor
                    }

                    RowLayout {
                        Layout.fillWidth: true

                        ComboBox {
                            id: apiTypeCombo
                            Layout.fillWidth: true
                            model: ["responses", "chat_completions"]
                            textRole: "text" // This is critical for ComboBox to display text properly
                            currentIndex: model.indexOf(currentSettings.api_type || "responses")

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: apiTypeCombo.displayText
                                color: foregroundColor
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }

                            popup.background: Rectangle {
                                color: backgroundColor
                                border.color: accentColor
                                border.width: 1
                                radius: 4
                            }
                        }

                        Button {
                            text: "?"
                            width: 25
                            height: 25

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "?"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: {
                                infoDialog.title = "API Type"
                                infoDialog.message = "Choose between:\n\n" +
                                    "- responses: New endpoint for single-turn completions\n" +
                                    "- chat_completions: Traditional chat endpoint for multi-turn conversations"
                                infoDialog.open()
                            }
                        }
                    }
                }
            }

            // Model Selection
            GroupBox {
                title: "Model Selection"
                Layout.fillWidth: true

                background: Rectangle {
                    color: Qt.rgba(0.27, 0.28, 0.35, 0.5)
                    radius: 4
                    border.color: accentColor
                    border.width: 1
                }

                label: Label {
                    text: parent.title
                    color: foregroundColor
                    font.bold: true
                    padding: 4
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    TabBar {
                        id: modelTabBar
                        Layout.fillWidth: true

                        TabButton {
                            text: "Models"
                            width: implicitWidth
                        }

                        TabButton {
                            text: "Dated Snapshots"
                            width: implicitWidth
                        }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        currentIndex: modelTabBar.currentIndex

                        // Main models
                        ComboBox {
                            id: modelCombo
                            Layout.fillWidth: true
                            model: mainModels
                            textRole: "text" // Critical for displaying the model name
                            valueRole: "value" // Use for getting the model id

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: modelCombo.displayText
                                color: foregroundColor
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }

                            popup.background: Rectangle {
                                color: backgroundColor
                                border.color: accentColor
                                border.width: 1
                                radius: 4
                            }

                            onCurrentIndexChanged: {
                                if (currentIndex >= 0) {
                                    const modelId = model[currentIndex].value
                                    updateModelInfo(modelId)
                                }
                            }
                        }

                        // Dated snapshots
                        ComboBox {
                            id: snapshotCombo
                            Layout.fillWidth: true
                            model: modelSnapshots
                            textRole: "text" // Critical for displaying the model name
                            valueRole: "value" // Use for getting the model id

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: snapshotCombo.displayText
                                color: foregroundColor
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }

                            popup.background: Rectangle {
                                color: backgroundColor
                                border.color: accentColor
                                border.width: 1
                                radius: 4
                            }

                            onCurrentIndexChanged: {
                                if (currentIndex >= 0) {
                                    const modelId = model[currentIndex].value
                                    updateModelInfo(modelId)
                                }
                            }
                        }
                    }

                    Label {
                        id: modelInfoLabel
                        text: "Context: 0 tokens | Max output: 0 tokens"
                        color: assistantMessageColor
                        font.italic: true
                        Layout.fillWidth: true
                    }

                    // Pricing information
                    Label {
                        id: pricingInfoLabel
                        text: "Pricing: Input: $0.00 | Output: $0.00 per 1M tokens"
                        color: assistantMessageColor
                        font.italic: true
                        Layout.fillWidth: true
                    }
                }
            }

            // Generation Parameters
            GroupBox {
                title: "Generation Parameters"
                Layout.fillWidth: true

                background: Rectangle {
                    color: Qt.rgba(0.27, 0.28, 0.35, 0.5)
                    radius: 4
                    border.color: accentColor
                    border.width: 1
                }

                label: Label {
                    text: parent.title
                    color: foregroundColor
                    font.bold: true
                    padding: 4
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 16

                    // Temperature
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Temperature:"
                            color: foregroundColor
                            Layout.preferredWidth: 100
                        }

                        Slider {
                            id: temperatureSlider
                            from: 0.0
                            to: 2.0
                            stepSize: 0.1
                            value: currentSettings.temperature !== undefined ? currentSettings.temperature : 0.7
                            Layout.fillWidth: true
                        }

                        Label {
                            text: temperatureSlider.value.toFixed(1)
                            color: foregroundColor
                            Layout.preferredWidth: 50
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    // Max Tokens
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Max Tokens:"
                            color: foregroundColor
                            Layout.preferredWidth: 100
                        }

                        Slider {
                            id: maxTokensSlider
                            from: 256
                            to: currentModelInfo.output_limit || 16384
                            stepSize: 256
                            value: currentSettings.max_output_tokens ||
                                   currentSettings.max_tokens ||
                                   currentSettings.max_completion_tokens ||
                                   1024
                            Layout.fillWidth: true
                        }

                        Label {
                            text: maxTokensSlider.value.toFixed(0)
                            color: foregroundColor
                            Layout.preferredWidth: 50
                            horizontalAlignment: Text.AlignRight
                        }

                        Button {
                            text: "Max"
                            width: 40
                            height: 25

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "Max"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: 10
                            }

                            onClicked: {
                                maxTokensSlider.value = maxTokensSlider.to
                            }
                        }
                    }

                    // Top P
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Top P:"
                            color: foregroundColor
                            Layout.preferredWidth: 100
                        }

                        Slider {
                            id: topPSlider
                            from: 0.0
                            to: 1.0
                            stepSize: 0.05
                            value: currentSettings.top_p !== undefined ? currentSettings.top_p : 1.0
                            Layout.fillWidth: true
                        }

                        Label {
                            text: topPSlider.value.toFixed(2)
                            color: foregroundColor
                            Layout.preferredWidth: 50
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    // Response Format
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Response Format:"
                            color: foregroundColor
                            Layout.preferredWidth: 120
                        }

                        ComboBox {
                            id: formatCombo
                            model: responseFormats
                            Layout.fillWidth: true
                            currentIndex: {
                                let format = "text"
                                if (currentSettings.text &&
                                    currentSettings.text.format &&
                                    currentSettings.text.format.type) {
                                    format = currentSettings.text.format.type
                                }
                                return model.indexOf(format)
                            }

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: formatCombo.displayText
                                color: foregroundColor
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                        }

                        Button {
                            text: "?"
                            width: 25
                            height: 25

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "?"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: {
                                infoDialog.title = "Response Format"
                                infoDialog.message = "When set to 'json_object', the response will be formatted as valid JSON.\n" +
                                    "This is useful when you need structured data from the model."
                                infoDialog.open()
                            }
                        }
                    }

                    // Reasoning Effort (Only shown for reasoning models)
                    RowLayout {
                        Layout.fillWidth: true
                        visible: isCurrentModelReasoning

                        Label {
                            text: "Reasoning Effort:"
                            color: foregroundColor
                            Layout.preferredWidth: 120
                        }

                        ComboBox {
                            id: reasoningEffortCombo
                            model: reasoningEfforts
                            Layout.fillWidth: true
                            currentIndex: {
                                let effort = "medium"
                                if (currentSettings.reasoning &&
                                    currentSettings.reasoning.effort) {
                                    effort = currentSettings.reasoning.effort
                                }
                                return model.indexOf(effort)
                            }

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: reasoningEffortCombo.displayText
                                color: foregroundColor
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                            }
                        }

                        Button {
                            text: "?"
                            width: 25
                            height: 25

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "?"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: {
                                infoDialog.title = "Reasoning Effort"
                                infoDialog.message = "Controls how much effort the model puts into reasoning:\n\n" +
                                    "- low: Minimal reasoning, faster responses\n" +
                                    "- medium: Balanced reasoning and speed\n" +
                                    "- high: Thorough reasoning, slower responses"
                                infoDialog.open()
                            }
                        }
                    }

                    // Streaming
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Stream Responses:"
                            color: foregroundColor
                            Layout.preferredWidth: 120
                        }

                        Item {
                            Layout.fillWidth: true
                        }

                        Switch {
                            id: streamingSwitch
                            checked: currentSettings.stream !== undefined ? currentSettings.stream : true
                        }
                    }

                    // Seed
                    RowLayout {
                        Layout.fillWidth: true

                        Label {
                            text: "Seed:"
                            color: foregroundColor
                            Layout.preferredWidth: 100
                        }

                        SpinBox {
                            id: seedSpinBox
                            from: -1
                            to: 2147483647
                            value: currentSettings.seed !== undefined ? currentSettings.seed : -1
                            Layout.fillWidth: true
                            editable: true

                            textFromValue: function (value, locale) {
                                return value === -1 ? "None" : value.toString()
                            }

                            valueFromText: function (text, locale) {
                                return text === "None" ? -1 : parseInt(text, 10)
                            }
                        }

                        Button {
                            text: "?"
                            width: 25
                            height: 25

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "?"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }

                            onClicked: {
                                infoDialog.title = "Seed"
                                infoDialog.message = "Setting a specific seed value helps generate more deterministic responses.\n" +
                                    "Using the same seed with the same parameters should return similar results."
                                infoDialog.open()
                            }
                        }
                    }
                }
            }

            // Buttons
            RowLayout {
                Layout.fillWidth: true
                spacing: 16

                Item {
                    Layout.fillWidth: true
                }

                Button {
                    text: "Cancel"
                    implicitWidth: 100

                    background: Rectangle {
                        color: highlightColor
                        radius: 4
                    }

                    contentItem: Text {
                        text: "Cancel"
                        color: foregroundColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: {
                        settingsDialog.reject()
                    }
                }

                Button {
                    text: "Save"
                    implicitWidth: 100

                    background: Rectangle {
                        color: accentColor
                        radius: 4
                    }

                    contentItem: Text {
                        text: "Save"
                        color: foregroundColor
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    onClicked: {
                        // Collect all settings
                        const settings = {
                            api_key: apiKeyField.text,
                            api_base: apiBaseField.text,
                            api_type: apiTypeCombo.currentText,
                            temperature: temperatureSlider.value,
                            top_p: topPSlider.value,
                            stream: streamingSwitch.checked,
                            text: {
                                format: {
                                    type: formatCombo.currentText
                                }
                            }
                        }

                        // Set the correct max tokens parameter based on API type
                        if (apiTypeCombo.currentText === "responses") {
                            settings.max_output_tokens = maxTokensSlider.value
                        } else {
                            settings.max_tokens = maxTokensSlider.value
                        }

                        // Add reasoning settings if it's a reasoning model
                        if (isCurrentModelReasoning) {
                            settings.reasoning = {
                                effort: reasoningEffortCombo.currentText
                            }
                        }

                        // Add seed if it's not "None"
                        if (seedSpinBox.value !== -1) {
                            settings.seed = seedSpinBox.value
                        }

                        // Set model based on which tab is active
                        if (modelTabBar.currentIndex === 0) {
                            // Main models
                            settings.model = mainModels[modelCombo.currentIndex].value
                        } else {
                            // Dated snapshots
                            settings.model = modelSnapshots[snapshotCombo.currentIndex].value
                        }

                        // Emit settings saved signal
                        settingsDialog.settingsSaved(settings)

                        // Close dialog
                        settingsDialog.accept()
                    }
                }
            }
        }
    }

    // Helper dialog for information popups
    Dialog {
        id: infoDialog
        title: "Information"
        modal: true

        property string message: ""

        contentItem: Rectangle {
            color: backgroundColor
            implicitWidth: 400
            implicitHeight: textLabel.implicitHeight + 32

            Text {
                id: textLabel
                anchors.fill: parent
                anchors.margins: 16
                text: infoDialog.message
                color: foregroundColor
                wrapMode: Text.WordWrap
            }
        }

        footer: DialogButtonBox {
            Button {
                text: "OK"
                DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole

                background: Rectangle {
                    color: accentColor
                    radius: 4
                }

                contentItem: Text {
                    text: "OK"
                    color: foregroundColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    // Initialize dialog with current settings
    function initialize(settings) {
        currentSettings = settings || {}

        // Fetch model data from view model
        mainModels = settingsViewModel.get_main_models()
        modelSnapshots = settingsViewModel.get_model_snapshots()
        reasoningEfforts = settingsViewModel.get_reasoning_efforts()
        responseFormats = settingsViewModel.get_response_formats()

        // Set current model index
        const currentModelId = currentSettings.model || "gpt-4o"

        // Try to find the model in the main models
        let foundInMain = false
        for (let i = 0; i < mainModels.length; i++) {
            if (mainModels[i].value === currentModelId) {
                modelCombo.currentIndex = i
                modelTabBar.currentIndex = 0
                foundInMain = true
                break
            }
        }

        // If not found in main models, try snapshots
        if (!foundInMain) {
            for (let i = 0; i < modelSnapshots.length; i++) {
                if (modelSnapshots[i].value === currentModelId) {
                    snapshotCombo.currentIndex = i
                    modelTabBar.currentIndex = 1
                    break
                }
            }
        }

        // Update model info for the current model
        updateModelInfo(currentModelId)
    }

    // Helper function to update model info display
    function updateModelInfo(modelId) {
        // Get model info from view model
        currentModelInfo = settingsViewModel.get_model_info(modelId)
        isCurrentModelReasoning = settingsViewModel.is_reasoning_model(modelId)

        // Update info text
        if (currentModelInfo) {
            const contextSize = currentModelInfo.context_size ? currentModelInfo.context_size.toLocaleString() : "Unknown"
            const outputLimit = currentModelInfo.output_limit ? currentModelInfo.output_limit.toLocaleString() : "Unknown"

            modelInfoLabel.text = `Context window: ${contextSize} tokens | Max output: ${outputLimit} tokens`

            // Update max tokens slider range
            if (currentModelInfo.output_limit) {
                maxTokensSlider.to = currentModelInfo.output_limit
            }

            // Update pricing info
            if (currentModelInfo.pricing) {
                const inputPrice = currentModelInfo.pricing.input ? currentModelInfo.pricing.input.toFixed(2) : "0.00"
                const outputPrice = currentModelInfo.pricing.output ? currentModelInfo.pricing.output.toFixed(2) : "0.00"

                pricingInfoLabel.text = `Pricing: Input: $${inputPrice} | Output: $${outputPrice} per 1M tokens`
            } else {
                pricingInfoLabel.text = "Pricing: No pricing information available"
            }
        } else {
            modelInfoLabel.text = "No model information available"
            pricingInfoLabel.text = "No pricing information available"
        }
    }

    // Connect UI elements to update model info when tab changes
    Connections {
        target: modelTabBar
        function onCurrentIndexChanged() {
            if (modelTabBar.currentIndex === 0 && modelCombo.currentIndex >= 0) {
                updateModelInfo(mainModels[modelCombo.currentIndex].value)
            } else if (modelTabBar.currentIndex === 1 && snapshotCombo.currentIndex >= 0) {
                updateModelInfo(modelSnapshots[snapshotCombo.currentIndex].value)
            }
        }
    }
}