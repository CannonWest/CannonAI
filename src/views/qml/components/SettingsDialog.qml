// src/views/qml/components/SettingsDialog.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
// Replace the old Qt5 dialogs import with Qt6 compatible one
import QtQuick.Dialogs

Dialog {
    id: settingsDialog
    title: "API Settings"
    width: 600
    height: 700
    modal: true

    // Properties to store current settings
    property var currentSettings: ({})

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
                            model: ListModel {
                                id: mainModelsModel
                                ListElement {
                                    text: "GPT-4o"; value: "gpt-4o"
                                }
                                ListElement {
                                    text: "GPT-4o Mini"; value: "gpt-4o-mini"
                                }
                                ListElement {
                                    text: "GPT-4 Turbo"; value: "gpt-4-turbo"
                                }
                                ListElement {
                                    text: "GPT-3.5 Turbo"; value: "gpt-3.5-turbo"
                                }
                                ListElement {
                                    text: "DeepSeek R1"; value: "deepseek-reasoner"
                                }
                                ListElement {
                                    text: "DeepSeek V3"; value: "deepseek-chat"
                                }
                            }

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

                            Component.onCompleted: {
                                // Set current index based on settings
                                for (let i = 0; i < mainModelsModel.count; i++) {
                                    if (mainModelsModel.get(i).value === currentSettings.model) {
                                        modelCombo.currentIndex = i
                                        break
                                    }
                                }
                            }
                        }

                        // Dated snapshots
                        ComboBox {
                            id: snapshotCombo
                            Layout.fillWidth: true
                            model: ListModel {
                                id: snapshotsModel
                                ListElement {
                                    text: "GPT-4.5 Turbo (2025-02-27)"; value: "gpt-4.5-preview-2025-02-27"
                                }
                                ListElement {
                                    text: "GPT-4o (2024-08-06)"; value: "gpt-4o-2024-08-06"
                                }
                                ListElement {
                                    text: "GPT-4o (2024-11-20)"; value: "gpt-4o-2024-11-20"
                                }
                                ListElement {
                                    text: "GPT-4o (2024-05-13)"; value: "gpt-4o-2024-05-13"
                                }
                                ListElement {
                                    text: "o1 (2024-12-17)"; value: "o1-2024-12-17"
                                }
                                ListElement {
                                    text: "o3-mini (2025-01-31)"; value: "o3-mini-2025-01-31"
                                }
                            }

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

                            Component.onCompleted: {
                                // Set current index based on settings
                                for (let i = 0; i < snapshotsModel.count; i++) {
                                    if (snapshotsModel.get(i).value === currentSettings.model) {
                                        snapshotCombo.currentIndex = i
                                        // Also switch to this tab since this is the selected model
                                        modelTabBar.currentIndex = 1
                                        break
                                    }
                                }
                            }
                        }
                    }

                    Label {
                        id: modelInfoLabel
                        text: "Context: 128K tokens | Max output: 4K tokens"
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
                            to: 16384
                            stepSize: 256
                            value: currentSettings.max_tokens || 1024
                            Layout.fillWidth: true
                        }

                        Label {
                            text: maxTokensSlider.value.toFixed(0)
                            color: foregroundColor
                            Layout.preferredWidth: 50
                            horizontalAlignment: Text.AlignRight
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
                            model: ["text", "json_object"]
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

                            // KEEP ONLY ONE DECLARATION
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
                            max_tokens: maxTokensSlider.value,
                            top_p: topPSlider.value,
                            stream: streamingSwitch.checked,
                            text: {
                                format: {
                                    type: formatCombo.currentText
                                }
                            }
                        }

                        // Add seed if it's not "None"
                        if (seedSpinBox.value !== -1) {
                            settings.seed = seedSpinBox.value
                        }

                        // Set model based on which tab is active
                        if (modelTabBar.currentIndex === 0) {
                            // Main models
                            settings.model = mainModelsModel.get(modelCombo.currentIndex).value
                        } else {
                            // Dated snapshots
                            settings.model = snapshotsModel.get(snapshotCombo.currentIndex).value
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

        // Update model info based on current model
        updateModelInfo()
    }

    // Update model info display based on selected model
    function updateModelInfo() {
        let modelId = ""

        // Get model ID based on active tab
        if (modelTabBar.currentIndex === 0) {
            // Main models tab
            if (modelCombo.currentIndex >= 0) {
                modelId = mainModelsModel.get(modelCombo.currentIndex).value
            }
        } else {
            // Dated snapshots tab
            if (snapshotCombo.currentIndex >= 0) {
                modelId = snapshotsModel.get(snapshotCombo.currentIndex).value
            }
        }

        // Update model info text (this would need to be connected to actual model data)
        let contextSize = 128000
        let outputLimit = 16384

        // Set model info text
        modelInfoLabel.text = `Context window: ${contextSize.toLocaleString()} tokens | Max output: ${outputLimit.toLocaleString()} tokens`
    }

    // Connect UI elements to update model info
    Connections {
        target: modelTabBar

        function onCurrentIndexChanged() {
            updateModelInfo()
        }
    }

    Connections {
        target: modelCombo

        function onCurrentIndexChanged() {
            if (modelTabBar.currentIndex === 0) updateModelInfo()
        }
    }

    Connections {
        target: snapshotCombo

        function onCurrentIndexChanged() {
            if (modelTabBar.currentIndex === 1) updateModelInfo()
        }
    }
}