// src/views/qml/MainWindow.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
// Import dialogs from Qt6
import QtQuick.Dialogs

// Import our custom components with a namespace
import "./components" as Components

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

    // Application state
    property bool isLoading: false
    property var currentConversation: null

    // Window properties
    color: backgroundColor

    // Menu bar
    menuBar: MenuBar {
        Menu {
            title: "File"

            MenuItem {
                text: "New Conversation"
                onTriggered: conversationViewModel.create_new_conversation("New Conversation")
            }

            Shortcut {
                sequence: "Ctrl+N"
                onActivated: conversationViewModel.create_new_conversation("New Conversation")
            }

            MenuItem {
                text: "Save Conversations"
                onTriggered: {
                    // Conversations are auto-saved, but we'll show a confirmation
                    saveDialog.open()
                }
            }

            Shortcut {
                sequence: "Ctrl+S"
                onActivated: saveDialog.open()
            }

            MenuSeparator {
            }

            MenuItem {
                text: "Exit"
                onTriggered: Qt.quit()
            }

            Shortcut {
                sequence: "Ctrl+Q"
                onActivated: Qt.quit()
            }
        }

        Menu {
            title: "Edit"

            MenuItem {
                text: "Rename Conversation"
                onTriggered: renameDialog.open()
            }

            Shortcut {
                sequence: "F2"
                onActivated: renameDialog.open()
            }

            MenuItem {
                text: "Duplicate Conversation"
                onTriggered: duplicateConversation()
            }

            Shortcut {
                sequence: "Ctrl+D"
                onActivated: duplicateConversation()
            }

            MenuItem {
                text: "Search Conversations"
                onTriggered: searchDialog.open()
            }

            Shortcut {
                sequence: "Ctrl+F"
                onActivated: searchDialog.open()
            }
        }

        Menu {
            title: "Settings"

            MenuItem {
                text: "API Settings"
                onTriggered: openSettingsDialog()
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

                            background: Rectangle {
                                color: highlightColor
                                radius: 4
                            }

                            contentItem: Text {
                                text: "+"
                                color: foregroundColor
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // Conversation list
                ListView {
                    id: conversationList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: ListModel {
                        id: conversationsModel
                    }

                    // Use our custom ConversationItem component as delegate
                    // With namespace prefix "Components."
                    delegate: Components.ConversationItem
                    {
                        width: conversationList.width

                        // Connect signals to slot methods
                        onItemClicked: {
                            conversationList.currentIndex = index
                            conversationViewModel.load_conversation(model.id)
                        }

                        onItemRightClicked: {
                            conversationList.currentIndex = index
                            contextMenu.popup()
                        }

                        onItemDoubleClicked: {
                            conversationList.currentIndex = index
                            renameDialog.open()
                        }
                    }

                    // Context menu for conversations
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
                            // when the current branch changes
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
                        model: ListModel {
                            id: messagesModel
                        }

                        // Use our custom MessageDelegate for message items
                        // With namespace prefix "Components."
                        delegate: Components.MessageDelegate
                        {
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
                    visible: isLoading

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

                                background: Rectangle {
                                    color: highlightColor
                                    radius: 4
                                    border.color: accentColor
                                    border.width: 1
                                }

                                contentItem: Text {
                                    text: "Clear All"
                                    color: foregroundColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        ListView {
                            id: attachmentsView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            orientation: ListView.Horizontal
                            spacing: 8
                            model: ListModel {
                                id: fileAttachmentsModel
                            }

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

                                        background: Rectangle {
                                            color: highlightColor
                                            radius: 2
                                        }

                                        contentItem: Text {
                                            text: "×"
                                            color: foregroundColor
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                        }
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
                                background: Rectangle {
                                    color: "transparent"
                                }
                                wrapMode: TextEdit.Wrap
                                enabled: !isLoading

                                // Enable Shift+Enter for newlines, Enter to send
                                Keys.onPressed: function (event) {
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
                                enabled: !isLoading && inputField.text.trim() !== ""
                                onClicked: sendMessage()

                                background: Rectangle {
                                    color: sendButton.enabled ? accentColor : Qt.rgba(0.27, 0.28, 0.35, 0.5)
                                    radius: 4
                                }

                                contentItem: Text {
                                    text: "Send"
                                    color: foregroundColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }

                            Button {
                                id: retryButton
                                text: "↺"
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                enabled: !isLoading && messagesModel.count > 0
                                onClicked: conversationViewModel.retry_last_response()

                                background: Rectangle {
                                    color: retryButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5)
                                    radius: 4
                                    border.color: accentColor
                                    border.width: 1
                                }

                                contentItem: Text {
                                    text: "↺"
                                    color: foregroundColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 18
                                }
                            }

                            Button {
                                id: attachButton
                                text: "📎"
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                enabled: !isLoading
                                onClicked: fileDialog.open()

                                background: Rectangle {
                                    color: attachButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5)
                                    radius: 4
                                    border.color: accentColor
                                    border.width: 1
                                }

                                contentItem: Text {
                                    text: "📎"
                                    color: foregroundColor
                                    horizontalAlignment: Text.AlignHCenter
                                    verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 18
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

    // Dialogs - Updated for Qt6 compatibility
    FileDialog {
        id: fileDialog
        title: "Attach File"
        // Multi-selection property in Qt6
        fileMode: FileDialog.OpenFiles
        onAccepted: processAttachments(selectedFiles)
    }

    Dialog {
        id: saveDialog
        title: "Save Conversations"
        standardButtons: Dialog.Ok
        modal: true

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }

        contentItem: Text {
            text: "All conversations have been saved."
            color: foregroundColor
            padding: 16
        }
    }
    
    Dialog {
        id: renameDialog
        title: "Rename Conversation"
        standardButtons: Dialog.Ok | Dialog.Cancel
        modal: true

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }
        onAccepted: {
            if (conversationList.currentIndex >= 0) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id
                conversationViewModel.rename_conversation(conversationId, renameField.text)
            }
        }
        contentItem: Item {  // Use Item as a wrapper that supports padding-like behavior
            implicitWidth: renameDialogColumnLayout.implicitWidth
            implicitHeight: renameDialogColumnLayout.implicitHeight + 32  // Add some extra space

            ColumnLayout {
                id: renameDialogColumnLayout  // Use a unique, specific ID to avoid conflicts
                anchors.fill: parent
                anchors.margins: 16  // Use margins instead of padding
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
    }
    Dialog {
        id: deleteConfirmDialog
        title: "Delete Conversation"
        standardButtons: Dialog.Yes | Dialog.No
        modal: true

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }

        onAccepted: {
            if (conversationList.currentIndex >= 0) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id
                conversationViewModel.delete_conversation(conversationId)
            }
        }

        contentItem: Text {
            text: "Are you sure you want to delete this conversation? This action cannot be undone."
            color: foregroundColor
            wrapMode: Text.WordWrap
            padding: 16
        }
    }

    Dialog {
        id: aboutDialog
        title: "About OpenAI Chat"
        standardButtons: Dialog.Close
        modal: true

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }

        contentItem: Item {  // Use Item as a wrapper that supports padding-like behavior
            implicitWidth: aboutDialogColumnLayout.implicitWidth
            implicitHeight: aboutDialogColumnLayout.implicitHeight + 32  // Add some extra space

            ColumnLayout {
                id: aboutDialogColumnLayout  // Use a unique, specific ID to avoid conflicts
                anchors.fill: parent
                anchors.margins: 16  // Use margins instead of padding
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
    }
    // Settings dialog - using our custom component
    // This is the component that was previously not found
    Components.SettingsDialog {
        id: settingsDialog
        width: 600
        height: 700

        // Connect the settings saved signal to our handler
        onSettingsSaved: function (settings) {
            settingsViewModel.update_settings(settings)
        }
    }

    // Helper functions
    function sendMessage() {
        if (inputField.text.trim() === "") return

        // Prepare file attachments
        let attachments = []
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            attachments.push({
                filePath: fileAttachmentsModel.get(i).filePath,
                fileName: fileAttachmentsModel.get(i).fileName
            })
        }

        // Get current conversation ID
        if (conversationList.currentIndex < 0 || !conversationsModel.count) {
            return // No active conversation
        }

        const conversationId = conversationsModel.get(conversationList.currentIndex).id

        // Send the message
        conversationViewModel.send_message(conversationId, inputField.text, attachments)

        // Clear input and attachments
        inputField.text = ""
        fileAttachmentsModel.clear()
    }

    function duplicateConversation() {
        if (conversationList.currentIndex < 0) return

        const sourceId = conversationsModel.get(conversationList.currentIndex).id
        const sourceName = conversationsModel.get(conversationList.currentIndex).name

        // This would call a method to duplicate the conversation
        // conversationViewModel.duplicate_conversation(sourceId, sourceName + " (Copy)")
    }

    function processAttachments(fileUrls) {
        for (var i = 0; i < fileUrls.length; i++) {
            // Process file and add to attachments
            const fileUrl = fileUrls[i]
            const fileName = fileUrl.toString().split('/').pop()

            fileAttachmentsModel.append({
                "fileName": fileName,
                "filePath": fileUrl,
                "fileSize": "—", // Size will be updated by backend
                "tokenCount": 0   // Token count will be updated by backend
            })
        }
    }

    function openSettingsDialog() {
        // Initialize settings dialog with current settings
        settingsDialog.initialize(settingsViewModel.get_settings())
        settingsDialog.open()
    }

    function updateBranchNavigation(branch) {
        // Clear current navigation bar
        while (branchNavRow.children.length > 0) {
            branchNavRow.children[0].destroy()
        }

        // Add navigation buttons for each node in the branch
        for (let i = 0; i < branch.length; i++) {
            const node = branch[i]

            // Skip system messages in navigation
            if (node.role === "system" && i > 0) continue

            // Create button text based on role
            let buttonText = ""
            if (node.role === "user") {
                buttonText = "👤 User"
            } else if (node.role === "assistant") {
                buttonText = "🤖 Assistant"
            } else {
                buttonText = "🔧 System"
            }

            // Create navigation button
            const button = Qt.createQmlObject(
                'import QtQuick 2.15; import QtQuick.Controls 2.15; ' +
                'Button { ' +
                '    text: "' + buttonText + '"; ' +
                '    property string nodeId: "' + node.id + '"; ' +
                '    background: Rectangle { ' +
                '        color: ' + (i === branch.length - 1 ? 'accentColor' : 'highlightColor') + '; ' +
                '        radius: 4; ' +
                '    } ' +
                '    contentItem: Text { ' +
                '        text: parent.text; ' +
                '        color: foregroundColor; ' +
                '    } ' +
                '}',
                branchNavRow,
                "navButton"
            )

            // Connect click event
            button.clicked.connect(function () {
                conversationViewModel.navigate_to_message(button.nodeId)
            })

            // Add arrow separator if not the last item
            if (i < branch.length - 1) {
                const arrow = Qt.createQmlObject(
                    'import QtQuick 2.15; Text { ' +
                    '    text: "→"; ' +
                    '    color: foregroundColor; ' +
                    '    verticalAlignment: Text.AlignVCenter; ' +
                    '}',
                    branchNavRow,
                    "arrow"
                )
            }
        }
    }

    // Connect to ViewModel signals
    Connections {
        target: conversationViewModel

        function onConversationLoaded(conversation) {
            // Update conversations list if needed
            let found = false
            for (let i = 0; i < conversationsModel.count; i++) {
                if (conversationsModel.get(i).id === conversation.id) {
                    conversationsModel.set(i, {
                        id: conversation.id,
                        name: conversation.name,
                        modified_at: conversation.modified_at
                    })
                    found = true
                    conversationList.currentIndex = i
                    break
                }
            }

            if (!found) {
                conversationsModel.append({
                    id: conversation.id,
                    name: conversation.name,
                    modified_at: conversation.modified_at
                })
                conversationList.currentIndex = conversationsModel.count - 1
            }

            // Save reference to current conversation
            currentConversation = conversation
        }

        function onMessageBranchChanged(branch) {
            // Clear messages model
            messagesModel.clear()

            // Add messages to the model
            for (let i = 0; i < branch.length; i++) {
                const node = branch[i]
                messagesModel.append({
                    id: node.id,
                    role: node.role,
                    content: node.content,
                    timestamp: node.timestamp,
                    attachments: node.file_attachments || []
                })
            }

            // Update branch navigation
            updateBranchNavigation(branch)
        }

        function onMessageStreamChunk(chunk) {
            // If we're streaming, update the last message with the new chunk
            if (messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1
                const lastMessage = messagesModel.get(lastIndex)

                // If the last message is from the assistant, update it
                if (lastMessage.role === "assistant") {
                    const currentContent = lastMessage.content
                    messagesModel.set(lastIndex, {content: currentContent + chunk})
                } else {
                    // If not, add a new assistant message
                    messagesModel.append({
                        id: "temp-" + Date.now(),
                        role: "assistant",
                        content: chunk,
                        timestamp: new Date().toISOString(),
                        attachments: []
                    })
                }
            } else {
                // If no messages, add a new assistant message
                messagesModel.append({
                    id: "temp-" + Date.now(),
                    role: "assistant",
                    content: chunk,
                    timestamp: new Date().toISOString(),
                    attachments: []
                })
            }
        }

        function onTokenUsageUpdated(usage) {
            // Update token usage display
            let tokenText = "Tokens: " + usage.completion_tokens + " / " + usage.total_tokens

            // Add reasoning tokens if available
            if (usage.completion_tokens_details && usage.completion_tokens_details.reasoning_tokens) {
                tokenText += " (" + usage.completion_tokens_details.reasoning_tokens + " reasoning)"
            }

            tokenUsageText.text = tokenText
        }

        function onLoadingStateChanged(loading) {
            // Update loading state
            isLoading = loading
        }
    }

    // On application startup
    Component.onCompleted: {
        // Load all conversations
        let conversations = conversationViewModel.get_all_conversations()

        // Clear and rebuild model
        conversationsModel.clear()
        for (let i = 0; i < conversations.length; i++) {
            conversationsModel.append(conversations[i])
        }

        // Load first conversation if available
        if (conversationsModel.count > 0) {
            conversationList.currentIndex = 0
            conversationViewModel.load_conversation(conversationsModel.get(0).id)
        } else {
            // Create a new conversation if none exists
            conversationViewModel.create_new_conversation("New Conversation")
        }
    }
}