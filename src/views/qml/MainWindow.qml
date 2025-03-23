// src/views/qml/MainWindow.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs 1.3
import QtGraphicalEffects 1.15

ApplicationWindow {
    id: mainWindow
    visible: true
    width: 1200
    height: 800
    title: "OpenAI Chat Interface"

    // Set dark theme colors
    property color backgroundColor: "#2B2B2B"
    property color foregroundColor: "#F8F8F2"
    property color accentColor: "#6272A4"
    property color highlightColor: "#44475A"
    property color userMessageColor: "#50FA7B"
    property color assistantMessageColor: "#8BE9FD"
    property color systemMessageColor: "#FFB86C"
    property color errorColor: "#FF5555"

    // References to ViewModels
    property var conversationViewModel
    property var settingsViewModel

    // Window properties
    color: backgroundColor

    // Menu bar
    menuBar: MenuBar {
        Menu {
            title: "File"

            MenuItem {
                text: "New Conversation"
                shortcut: "Ctrl+N"
                onTriggered: conversationViewModel.create_new_conversation("New Conversation")
            }

            MenuItem {
                text: "Save Conversations"
                shortcut: "Ctrl+S"
                onTriggered: {
                    // Conversations are auto-saved, but we'll show a confirmation
                    saveDialog.open()
                }
            }

            MenuSeparator { }

            MenuItem {
                text: "Exit"
                shortcut: "Ctrl+Q"
                onTriggered: Qt.quit()
            }
        }

        Menu {
            title: "Edit"

            MenuItem {
                text: "Rename Conversation"
                shortcut: "F2"
                onTriggered: renameDialog.open()
            }

            MenuItem {
                text: "Duplicate Conversation"
                shortcut: "Ctrl+D"
                onTriggered: duplicateConversation()
            }

            MenuItem {
                text: "Search Conversations"
                shortcut: "Ctrl+F"
                onTriggered: searchDialog.open()
            }
        }

        Menu {
            title: "Settings"

            MenuItem {
                text: "API Settings"
                onTriggered: settingsDialog.open()
            }
        }

        Menu {
            title: "Help"

            MenuItem {
                text: "About"
                onTriggered: aboutDialog.open()
            }
        }
    }

    // Main content
    SplitView {
        id: mainSplitView
        anchors.fill: parent
        orientation: Qt.Horizontal

        // Sidebar with conversation list
        Rectangle {
            id: sidebarContainer
            SplitView.preferredWidth: 250
            SplitView.minimumWidth: 180
            color: highlightColor

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                // Header with title and new button
                Rectangle {
                    Layout.fillWidth: true
                    height: 40
                    color: accentColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8

                        Text {
                            text: "Conversations"
                            color: foregroundColor
                            font.pixelSize: 16
                            font.bold: true
                            Layout.fillWidth: true
                        }

                        Button {
                            text: "+"
                            onClicked: conversationViewModel.create_new_conversation("New Conversation")
                            ToolTip.text: "New Conversation"
                            ToolTip.visible: hovered
                            ToolTip.delay: 500
                        }
                    }
                }

                // Conversation list
                ListView {
                    id: conversationList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: ListModel { id: conversationsModel }

                    delegate: Rectangle {
                        width: conversationList.width
                        height: 50
                        color: ListView.isCurrentItem ? accentColor : "transparent"

                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                conversationList.currentIndex = index
                                conversationViewModel.load_conversation(model.id)
                            }
                            onDoubleClicked: renameDialog.open()

                            // Right-click context menu
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.RightButton) {
                                    contextMenu.popup()
                                }
                            }

                            Menu {
                                id: contextMenu
                                MenuItem {
                                    text: "Rename"
                                    onTriggered: renameDialog.open()
                                }
                                MenuItem {
                                    text: "Duplicate"
                                    onTriggered: duplicateConversation()
                                }
                                MenuItem {
                                    text: "Delete"
                                    onTriggered: deleteConfirmDialog.open()
                                }
                            }
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 8

                            Text {
                                text: model.name
                                color: foregroundColor
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Text {
                                text: formatDate(model.modified_at)
                                color: foregroundColor
                                opacity: 0.6
                                font.pixelSize: 10
                            }
                        }
                    }
                }
            }
        }

        // Main chat area
        Rectangle {
            id: chatContainer
            SplitView.fillWidth: true
            color: backgroundColor

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8

                // Branch navigation bar
                Rectangle {
                    id: branchNavBar
                    Layout.fillWidth: true
                    height: 50
                    color: highlightColor
                    radius: 4

                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 4
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOn
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

                        Row {
                            id: branchNavRow
                            spacing: 8
                            anchors.verticalCenter: parent.verticalCenter
                            // This will be filled with branch buttons dynamically
                        }
                    }
                }

                // Chat messages area
                ScrollView {
                    id: messagesScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOn

                    ListView {
                        id: messagesView
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 16
                        verticalLayoutDirection: ListView.TopToBottom
                        model: ListModel { id: messagesModel }

                        delegate: MessageDelegate {
                            width: messagesView.width - 16
                        }

                        // Auto-scroll to bottom when new messages are added
                        onCountChanged: {
                            if (atYEnd || contentHeight < height) {
                                messagesView.positionViewAtEnd()
                            }
                        }
                    }
                }

                // Thinking/Loading indicator
                Rectangle {
                    id: thinkingIndicator
                    Layout.fillWidth: true
                    height: 30
                    color: highlightColor
                    radius: 4
                    visible: false

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8

                        BusyIndicator {
                            width: 20
                            height: 20
                            running: thinkingIndicator.visible
                        }

                        Text {
                            text: "Thinking..."
                            color: foregroundColor
                            Layout.fillWidth: true
                        }
                    }
                }

                // File attachments area
                Rectangle {
                    id: attachmentsArea
                    Layout.fillWidth: true
                    height: 60
                    color: highlightColor
                    radius: 4
                    visible: fileAttachmentsModel.count > 0

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: "File Attachments: " + fileAttachmentsModel.count
                                color: foregroundColor
                                Layout.fillWidth: true
                            }

                            Button {
                                text: "Clear All"
                                onClicked: fileAttachmentsModel.clear()
                            }
                        }

                        ListView {
                            id: attachmentsView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            orientation: ListView.Horizontal
                            spacing: 8
                            model: ListModel { id: fileAttachmentsModel }

                            delegate: Rectangle {
                                width: 150
                                height: attachmentsView.height
                                color: accentColor
                                radius: 4

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    spacing: 4

                                    Text {
                                        text: model.fileName
                                        color: foregroundColor
                                        elide: Text.ElideMiddle
                                        Layout.fillWidth: true
                                    }

                                    Button {
                                        text: "×"
                                        width: 20
                                        height: 20
                                        onClicked: fileAttachmentsModel.remove(index)
                                    }
                                }
                            }
                        }
                    }
                }

                // Input area
                Rectangle {
                    id: inputArea
                    Layout.fillWidth: true
                    height: Math.min(Math.max(inputField.contentHeight + 40, 80), 200)
                    color: highlightColor
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            TextArea {
                                id: inputField
                                placeholderText: "Type your message here..."
                                color: foregroundColor
                                background: Rectangle { color: "transparent" }
                                wrapMode: TextEdit.Wrap

                                // Enable Shift+Enter for newlines, Enter to send
                                Keys.onPressed: function(event) {
                                    if (event.key === Qt.Key_Return && !event.modifiers) {
                                        sendMessage()
                                        event.accepted = true
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 40
                            spacing: 8

                            Button {
                                id: sendButton
                                text: "Send"
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                onClicked: sendMessage()
                                background: Rectangle {
                                    color: accentColor
                                    radius: 4
                                }
                            }

                            Button {
                                id: retryButton
                                text: "↺"
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                onClicked: conversationViewModel.retry_last_response()
                                background: Rectangle {
                                    color: highlightColor
                                    radius: 4
                                }
                            }

                            Button {
                                id: attachButton
                                text: "📎"
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                onClicked: fileDialog.open()
                                background: Rectangle {
                                    color: highlightColor
                                    radius: 4
                                }
                            }
                        }
                    }
                }

                // Token usage and model info
                Rectangle {
                    id: statusBar
                    Layout.fillWidth: true
                    height: 30
                    color: highlightColor
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8

                        Text {
                            id: tokenUsageText
                            text: "Tokens: 0"
                            color: foregroundColor
                            opacity: 0.8
                            Layout.fillWidth: true
                        }

                        Text {
                            id: modelInfoText
                            text: "Model: -"
                            color: foregroundColor
                            opacity: 0.8
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                        }
                    }
                }
            }
        }
    }

    // Component for message delegates
    Component {
        id: messageDelegate

        Rectangle {
            id: messageContainer
            width: parent.width
            height: messageContentColumn.height + 24
            color: {
                if (model.role === "user") return Qt.rgba(0.31, 0.98, 0.48, 0.1)
                else if (model.role === "assistant") return Qt.rgba(0.55, 0.91, 0.99, 0.1)
                else if (model.role === "system") return Qt.rgba(1.0, 0.72, 0.42, 0.1)
                else return Qt.rgba(0.27, 0.27, 0.35, 0.1)
            }
            radius: 8

            ColumnLayout {
                id: messageContentColumn
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: {
                            if (model.role === "user") return "👤 You:"
                            else if (model.role === "assistant") return "🤖 Assistant:"
                            else if (model.role === "system") return "🔧 System:"
                            else return model.role + ":"
                        }
                        color: {
                            if (model.role === "user") return userMessageColor
                            else if (model.role === "assistant") return assistantMessageColor
                            else if (model.role === "system") return systemMessageColor
                            else return foregroundColor
                        }
                        font.bold: true
                    }

                    Text {
                        text: formatDate(model.timestamp)
                        color: foregroundColor
                        opacity: 0.6
                        font.pixelSize: 10
                        horizontalAlignment: Text.AlignRight
                        Layout.fillWidth: true
                    }
                }

                // Message content with Markdown support
                Text {
                    id: messageText
                    text: formatMarkdown(model.content)
                    color: foregroundColor
                    wrapMode: Text.WordWrap
                    textFormat: Text.RichText
                    Layout.fillWidth: true
                    onLinkActivated: Qt.openUrlExternally(link)
                }

                // File attachments
                ListView {
                    id: messageAttachments
                    visible: model.attachments && model.attachments.length > 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? contentHeight : 0
                    model: messageAttachmentsModel
                    spacing: 4
                    interactive: false

                    ListModel {
                        id: messageAttachmentsModel
                        Component.onCompleted: {
                            if (model.attachments) {
                                for (let i = 0; i < model.attachments.length; i++) {
                                    messageAttachmentsModel.append(model.attachments[i])
                                }
                            }
                        }
                    }

                    delegate: Rectangle {
                        width: messageAttachments.width
                        height: 30
                        color: accentColor
                        radius: 4

                        Text {
                            anchors.fill: parent
                            anchors.margins: 4
                            text: model.fileName + " (" + model.fileSize + ", " + model.tokenCount + " tokens)"
                            color: foregroundColor
                            elide: Text.ElideMiddle
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
            }
        }
    }

    // Dialogs
    FileDialog {
        id: fileDialog
        title: "Attach File"
        selectMultiple: true
        onAccepted: {
            for (var i = 0; i < fileUrls.length; i++) {
                // Process file and add to attachments
                const fileUrl = fileUrls[i]
                const fileName = fileUrl.toString().split('/').pop()

                fileAttachmentsModel.append({
                    "fileName": fileName,
                    "filePath": fileUrl,
                    "fileSize": "0 KB",
                    "tokenCount": 0
                })

                // This would call a file processing function
                // processFile(fileUrl)
            }
        }
    }

    Dialog {
        id: saveDialog
        title: "Save Conversations"
        standardButtons: Dialog.Ok
        modal: true

        Text {
            text: "All conversations have been saved."
            color: foregroundColor
        }
    }

    Dialog {
        id: renameDialog
        title: "Rename Conversation"
        standardButtons: Dialog.Ok | Dialog.Cancel
        modal: true

        onAccepted: {
            if (conversationList.currentIndex >= 0) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id
                conversationViewModel.rename_conversation(conversationId, renameField.text)
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 16

            Text {
                text: "Enter new conversation name:"
                color: foregroundColor
            }

            TextField {
                id: renameField
                Layout.fillWidth: true
                color: foregroundColor
                background: Rectangle {
                    color: highlightColor
                    radius: 4
                }

                Component.onCompleted: {
                    if (conversationList.currentIndex >= 0) {
                        text = conversationsModel.get(conversationList.currentIndex).name
                    }
                }
            }
        }
    }

    Dialog {
        id: deleteConfirmDialog
        title: "Delete Conversation"
        standardButtons: Dialog.Yes | Dialog.No
        modal: true

        onAccepted: {
            if (conversationList.currentIndex >= 0) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id
                conversationViewModel.delete_conversation(conversationId)
            }
        }

        Text {
            text: "Are you sure you want to delete this conversation? This action cannot be undone."
            color: foregroundColor
            wrapMode: Text.WordWrap
        }
    }

    Dialog {
        id: aboutDialog
        title: "About OpenAI Chat"
        standardButtons: Dialog.Close
        modal: true

        ColumnLayout {
            anchors.fill: parent
            spacing: 16

            Text {
                text: "OpenAI Chat Interface"
                color: foregroundColor
                font.bold: true
                font.pixelSize: 16
            }

            Text {
                text: "A desktop application for interacting with OpenAI's language models.\n\n" +
                      "Features include:\n" +
                      "- Multiple conversations\n" +
                      "- Branching conversations with retries\n" +
                      "- Model customization\n" +
                      "- Conversation saving and loading"
                color: foregroundColor
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    Dialog {
        id: settingsDialog
        title: "API Settings"
        standardButtons: Dialog.Save | Dialog.Cancel
        modal: true
        width: 600
        height: 700

        onAccepted: {
            // Save settings
            settingsViewModel.save_settings({
                "api_key": apiKeyField.text,
                "api_base": apiBaseField.text,
                "api_type": apiTypeCombo.currentText,
                "model": modelCombo.currentText,
                "temperature": temperatureSlider.value,
                "max_tokens": maxTokensSlider.value,
                "stream": streamingCheckbox.checked
            })
        }

        ScrollView {
            anchors.fill: parent

            ColumnLayout {
                width: parent.width
                spacing: 16

                GroupBox {
                    title: "API Configuration"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "API Key:"
                            color: foregroundColor
                        }

                        TextField {
                            id: apiKeyField
                            Layout.fillWidth: true
                            echoMode: TextInput.Password
                            placeholderText: "Enter your OpenAI API key"
                        }

                        Text {
                            text: "API Base URL:"
                            color: foregroundColor
                        }

                        TextField {
                            id: apiBaseField
                            Layout.fillWidth: true
                            placeholderText: "https://api.openai.com/v1"
                        }

                        Text {
                            text: "API Type:"
                            color: foregroundColor
                        }

                        ComboBox {
                            id: apiTypeCombo
                            Layout.fillWidth: true
                            model: ["responses", "chat_completions"]
                        }
                    }
                }

                GroupBox {
                    title: "Model Selection"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8

                        Text {
                            text: "Model:"
                            color: foregroundColor
                        }

                        ComboBox {
                            id: modelCombo
                            Layout.fillWidth: true
                            model: ListModel {
                                ListElement { text: "GPT-4o"; value: "gpt-4o" }
                                ListElement { text: "GPT-4o Mini"; value: "gpt-4o-mini" }
                                ListElement { text: "GPT-4 Turbo"; value: "gpt-4-turbo" }
                                ListElement { text: "GPT-3.5 Turbo"; value: "gpt-3.5-turbo" }
                            }
                        }

                        Text {
                            id: modelInfoText
                            text: "Context: 128K tokens | Max output: 4K tokens"
                            color: foregroundColor
                            opacity: 0.7
                        }
                    }
                }

                GroupBox {
                    title: "Generation Parameters"
                    Layout.fillWidth: true

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 16

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: "Temperature:"
                                color: foregroundColor
                                Layout.preferredWidth: 100
                            }

                            Slider {
                                id: temperatureSlider
                                from: 0.0
                                to: 2.0
                                stepSize: 0.1
                                value: 0.7
                                Layout.fillWidth: true
                            }

                            Text {
                                text: temperatureSlider.value.toFixed(1)
                                color: foregroundColor
                                Layout.preferredWidth: 50
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: "Max Tokens:"
                                color: foregroundColor
                                Layout.preferredWidth: 100
                            }

                            Slider {
                                id: maxTokensSlider
                                from: 256
                                to: 4096
                                stepSize: 256
                                value: 1024
                                Layout.fillWidth: true
                            }

                            Text {
                                text: maxTokensSlider.value.toFixed(0)
                                color: foregroundColor
                                Layout.preferredWidth: 50
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true

                            Text {
                                text: "Streaming:"
                                color: foregroundColor
                                Layout.preferredWidth: 100
                            }

                            Item {
                                Layout.fillWidth: true
                            }

                            CheckBox {
                                id: streamingCheckbox
                                checked: true
                                Layout.preferredWidth: 50
                            }
                        }
                    }
                }
            }
        }
    }

    // Helper functions
    function formatDate(dateString) {
        if (!dateString) return "";

        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) {
            return "just now";
        } else if (diffMins < 60) {
            return diffMins + " min ago";
        } else if (diffHours < 24) {
            return diffHours + " hr ago";
        } else if (diffDays < 7) {
            return diffDays + " day" + (diffDays > 1 ? "s" : "") + " ago";
        } else {
            return date.toLocaleDateString();
        }
    }

    function formatMarkdown(text) {
        if (!text) return "";

        // Convert code blocks
        text = text.replace(/```(\w+)?\n([\s\S]*?)\n```/g, function(match, lang, code) {
            return '<pre style="background-color:#2d2d2d; color:#f8f8f2; padding:10px; border-radius:5px; overflow:auto;">' +
                   code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>';
        });

        // Convert inline code
        text = text.replace(/`([^`]+)`/g, '<code style="background-color:#2d2d2d; padding:2px 4px; border-radius:3px;">$1</code>');

        // Convert bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
        text = text.replace(/__([^_]+)__/g, '<b>$1</b>');

        // Convert italic
        text = text.replace(/\*([^*]+)\*/g, '<i>$1</i>');
        text = text.replace(/_([^_]+)_/g, '<i>$1</i>');

        // Convert headers
        text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
        text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');

        // Convert lists
        text = text.replace(/^- (.+)$/gm, '• $1<br>');
        text = text.replace(/^\* (.+)$/gm, '• $1<br>');
        text = text.replace(/^(\d+)\. (.+)$/gm, '$1. $2<br>');

        // Convert links
        text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color: #8BE9FD;">$1</a>');

        // Convert newlines
        text = text.replace(/\n/g, '<br>');

        return text;
    }

    function sendMessage() {
        if (inputField.text.trim() === "") return;

        // Prepare file attachments
        let attachments = [];
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            attachments.push({
                filePath: fileAttachmentsModel.get(i).filePath,
                fileName: fileAttachmentsModel.get(i).fileName
            });
        }

        // Get current conversation ID
        const conversationId = conversationsModel.get(conversationList.currentIndex).id;

        // Send the message
        conversationViewModel.send_message(conversationId, inputField.text, attachments);

        // Clear input and attachments
        inputField.text = "";
        fileAttachmentsModel.clear();
    }

    function duplicateConversation() {
        if (conversationList.currentIndex < 0) return;

        const sourceId = conversationsModel.get(conversationList.currentIndex).id;
        const sourceName = conversationsModel.get(conversationList.currentIndex).name;

        // This would call a method to duplicate the conversation
        // conversationViewModel.duplicate_conversation(sourceId, sourceName + " (Copy)");
    }

    // Load saved conversations on startup
    Component.onCompleted: {
        // Connect to ViewModel signals
        conversationViewModel.conversationLoaded.connect(function(conversation) {
            // Update conversations list if needed
            let found = false;
            for (let i = 0; i < conversationsModel.count; i++) {
                if (conversationsModel.get(i).id === conversation.id) {
                    conversationsModel.set(i, {
                        id: conversation.id,
                        name: conversation.name,
                        modified_at: conversation.modified_at
                    });
                    found = true;
                    break;
                }
            }

            if (!found) {
                conversationsModel.append({
                    id: conversation.id,
                    name: conversation.name,
                    modified_at: conversation.modified_at
                });
            }

            // Set as current conversation
            for (let i = 0; i < conversationsModel.count; i++) {
                if (conversationsModel.get(i).id === conversation.id) {
                    conversationList.currentIndex = i;
                    break;
                }
            }
        });

        conversationViewModel.messageBranchChanged.connect(function(branch) {
            // Clear current branch navigation
            while (branchNavRow.children.length > 0) {
                branchNavRow.children[0].destroy();
            }

            // Clear messages model
            messagesModel.clear();

            // Add branch navigation buttons
            for (let i = 0; i < branch.length; i++) {
                const node = branch[i];

                // Skip system messages in navigation
                if (node.role === "system" && i > 0) continue;

                // Create navigation button
                const navButton = Qt.createQmlObject(
                    'import QtQuick 2.15; import QtQuick.Controls 2.15; Button { text: "' +
                    (node.role === "user" ? "👤 User" :
                     node.role === "assistant" ? "🤖 Assistant" :
                     "🔧 System") +
                    '"; property string nodeId: "' + node.id + '"; }',
                    branchNavRow,
                    "navButton"
                );

                navButton.clicked.connect(function() {
                    conversationViewModel.navigate_to_message(navButton.nodeId);
                });

                // Highlight current node
                if (i === branch.length - 1) {
                    navButton.background = Qt.createQmlObject(
                        'import QtQuick 2.15; Rectangle { color: accentColor; radius: 4; }',
                        navButton,
                        "navButtonBackground"
                    );
                }

                // Add arrow separator if not the last item
                if (i < branch.length - 1) {
                    const arrow = Qt.createQmlObject(
                        'import QtQuick 2.15; Text { text: "→"; color: foregroundColor; }',
                        branchNavRow,
                        "arrow"
                    );
                }

                // Add messages to the display
                messagesModel.append({
                    id: node.id,
                    role: node.role,
                    content: node.content,
                    timestamp: node.timestamp,
                    attachments: node.file_attachments || []
                });
            }
        });

        conversationViewModel.messageStreamChunk.connect(function(chunk) {
            // If we're streaming, update the last message with the new chunk
            if (messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1;
                const lastMessage = messagesModel.get(lastIndex);

                // If the last message is from the assistant, update it
                if (lastMessage.role === "assistant") {
                    const currentContent = lastMessage.content;
                    messagesModel.set(lastIndex, { content: currentContent + chunk });
                } else {
                    // If not, add a new assistant message
                    messagesModel.append({
                        id: "temp-" + Date.now(),
                        role: "assistant",
                        content: chunk,
                        timestamp: new Date().toISOString(),
                        attachments: []
                    });
                }
            } else {
                // If no messages, add a new assistant message
                messagesModel.append({
                    id: "temp-" + Date.now(),
                    role: "assistant",
                    content: chunk,
                    timestamp: new Date().toISOString(),
                    attachments: []
                });
            }
        });

        conversationViewModel.tokenUsageUpdated.connect(function(usage) {
            tokenUsageText.text = "Tokens: " + usage.completion_tokens + " / " + usage.total_tokens;
            if (usage.reasoning_tokens) {
                tokenUsageText.text += " (" + usage.reasoning_tokens + " reasoning)";
            }
        });

        conversationViewModel.loadingStateChanged.connect(function(isLoading) {
            thinkingIndicator.visible = isLoading;
            sendButton.enabled = !isLoading;
            inputField.enabled = !isLoading;
        });

        // Load all conversations
        let conversations = conversationViewModel.get_all_conversations();
        for (let i = 0; i < conversations.length; i++) {
            conversationsModel.append(conversations[i]);
        }

        // Load first conversation if available
        if (conversationsModel.count > 0) {
            conversationList.currentIndex = 0;
            conversationViewModel.load_conversation(conversationsModel.get(0).id);
        } else {
            // Create a new conversation if none exists
            conversationViewModel.create_new_conversation("New Conversation");
        }
    }
}