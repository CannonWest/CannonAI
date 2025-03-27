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
    objectName: "mainWindow"  // Add this line
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

    signal fileRequested(var fileUrl)

    signal errorOccurred(string errorMessage)

    signal cleanupRequested()

    function initializeApp() {
        try {
            // Try to get all conversations
            console.log("Getting all conversations");
            let conversations = conversationViewModel.get_all_conversations();
            console.log(`Got ${conversations ? conversations.length : 0} conversations`);

            // Clear and rebuild model
            conversationsModel.clear();

            if (conversations && conversations.length > 0) {
                console.log("Loading existing conversations");

                // Add conversations to model
                for (let i = 0; i < conversations.length; i++) {
                    conversationsModel.append(conversations[i]);
                }

                // Load first conversation if available
                if (conversationsModel.count > 0) {
                    console.log("Loading first conversation");
                    conversationList.currentIndex = 0;
                    conversationViewModel.load_conversation(conversationsModel.get(0).id);
                }
            } else {
                console.log("No conversations found, creating new one");
                // Create a new conversation if none exists
                conversationViewModel.create_new_conversation("New Conversation");
            }
        } catch (e) {
            console.error("Error initializing application:", e);
            // Show error to user
            errorDialog.title = "Initialization Error";
            errorDialog.message = "Failed to initialize application: " + e;
            errorDialog.open();

            // Try to create a new conversation as fallback
            try {
                console.log("Creating fallback conversation");
                conversationViewModel.create_new_conversation("New Conversation");
            } catch (fallbackError) {
                console.error("Error creating fallback conversation:", fallbackError);
            }
        }
    }

    // Handle conversationsModel updates from Python
    function updateConversationsModel(conversations) {
        // Clear the model first
        conversationsModel.clear();

        // Add all conversations
        for (let i = 0; i < conversations.length; i++) {
            conversationsModel.append(conversations[i]);
        }

        // Select the first conversation if available
        if (conversationsModel.count > 0) {
            conversationList.currentIndex = 0;
        }
    }

    // Add connections to the asyncHelper
    Connections {
        target: asyncHelper

        function onTaskStarted(taskId) {
            console.log("Async task started: " + taskId);

            // Show loading indicators based on task type
            if (taskId.startsWith("search_")) {
                searchingIndicator.visible = true;
            } else if (taskId.startsWith("load_")) {
                // Show loading state for data loading
                loadingIndicator.visible = true;
            }
        }

        function onTaskFinished(taskId, result) {
            console.log("Task finished: " + taskId);

            // Handle different task types
            if (taskId.startsWith("search_")) {
                // Handle search results
                searchingIndicator.visible = false;

                // Clear previous results
                searchResultsModel.clear();

                // Populate results model
                if (result && result.length > 0) {
                    for (let i = 0; i < result.length; i++) {
                        searchResultsModel.append(result[i]);
                    }
                }
            } else if (taskId.startsWith("load_conversations")) {
                // Handle loaded conversations
                loadingIndicator.visible = false;

                // Update conversations model
                updateConversationsModel(result);
            } else if (taskId.startsWith("file_")) {
                // Handle file processing results
                updateFileInfo(result);
            }
        }

        function onTaskError(taskId, errorMessage) {
            console.error("Task error: " + taskId + " - " + errorMessage);

            // Hide loading indicators
            searchingIndicator.visible = false;
            loadingIndicator.visible = false;

            // Show error to user
            errorDialog.title = "Error";
            errorDialog.message = errorMessage;
            errorDialog.open();
        }

        function onTaskProgress(taskId, progress) {
            console.log("Task progress: " + taskId + " - " + progress + "%");

            // Update progress indicators
            if (taskId.startsWith("file_")) {
                // Update file processing progress
                updateFileProgress(taskId.split("_")[1], progress);
            }
        }
    }

    // Updated performSearch function to use asyncHelper
    function performSearch() {
        const searchTerm = searchField.text.trim();
        if (searchTerm === "") return;

        // Clear previous results
        searchResultsModel.clear();

        // Call the async helper to run the search
        asyncHelper.run_async_task(
            "search",
            "search_conversations",
            [searchTerm, searchAllConversations ? null : currentConversationId]
        );
    }

    // Function to be called during initialization to load conversations
    function loadAllConversations() {
        // Use the async helper
        asyncHelper.run_async_task(
            "load_conversations",
            "get_all_conversations",
            []
        );
    }

    // Example of handling file uploads asynchronously
    function handleFileSelected(fileUrl) {
        // Extract filename
        const fileName = fileUrl.toString().split('/').pop();

        // Add to model with placeholder info
        fileAttachmentsModel.append({
            "fileName": fileName,
            "filePath": fileUrl,
            "fileSize": "Processing...",
            "tokenCount": 0
        });

        // Start async processing
        asyncHelper.run_async_task(
            "file_" + fileName,
            "process_file",
            [fileUrl]
        );
    }

    onClosing: function (close) {
        console.log("Window closing event received")
        // Emit a signal to Python to start cleanup
        cleanupRequested()
    }

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
                            onClicked: {
                                if (typeof conversationViewModel !== "undefined" && conversationViewModel) {
                                    try {
                                        console.log("Create new conversation button clicked");
                                        conversationViewModel.create_new_conversation("New Conversation");
                                    } catch (e) {
                                        console.error("Error creating conversation:", e);
                                        // Show error to user
                                        errorDialog.title = "Error";
                                        errorDialog.message = "Failed to create new conversation: " + e;
                                        errorDialog.open();
                                    }
                                } else {
                                    console.error("conversationViewModel is not available!");
                                    // Try to create a conversation after a short delay
                                    createConvTimer.start();
                                }
                            }
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

                        // Add this timer to the same parent element as the button
                        Timer {
                            id: createConvTimer
                            interval: 500
                            repeat: false
                            onTriggered: {
                                if (typeof conversationViewModel !== "undefined" && conversationViewModel) {
                                    console.log("Creating conversation after delay");
                                    conversationViewModel.create_new_conversation("New Conversation");
                                } else {
                                    console.error("conversationViewModel still not available after delay");
                                    errorDialog.title = "Error";
                                    errorDialog.message = "Could not connect to application backend. Please restart the application.";
                                    errorDialog.open();
                                }
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
        Dialog {
            id: errorDialog
            title: "Error"
            modal: true
            // Remove implicit width binding and set explicit width
            width: 400
            property string message: ""

            background: Rectangle {
                color: backgroundColor
                radius: 8
                border.color: errorColor
                border.width: 1
            }

            contentItem: Text {
                text: errorDialog.message
                color: foregroundColor
                wrapMode: Text.WordWrap
                width: errorDialog.width - 32  // Use explicit width calculation
                padding: 16
            }

            standardButtons: Dialog.Ok
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
        // Set explicit width to avoid binding loop
        width: 400

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }

        contentItem: Text {
            text: "All conversations have been saved."
            color: foregroundColor
            width: saveDialog.width - 32  // Use explicit width calculation
            padding: 16
        }
    }

    Dialog {
        id: renameDialog
        title: "Rename Conversation"
        standardButtons: Dialog.Ok | Dialog.Cancel
        modal: true
        width: 400  // Set explicit width
        // Remove any binding to contentItem.implicitWidth

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

        contentItem: ColumnLayout {
            spacing: 16
            width: parent.width - 32  // Use explicit width calculation instead of implicitWidth binding

            Text {
                text: "Enter new conversation name:"
                color: foregroundColor
                Layout.fillWidth: true
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
        id: aboutDialog
        title: "About OpenAI Chat"
        standardButtons: Dialog.Close
        modal: true
        width: 400  // Set explicit width

        background: Rectangle {
            color: backgroundColor
            radius: 8
            border.color: accentColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: 16
            width: parent.width - 32

            Text {
                text: "OpenAI Chat Interface"
                color: foregroundColor
                font.bold: true
                font.pixelSize: 16
                Layout.fillWidth: true
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

        // Call the ViewModel method to duplicate the conversation
        conversationViewModel.duplicate_conversation(sourceId, sourceName + " (Copy)")
    }

    function processAttachments(fileUrls) {
        for (var i = 0; i < fileUrls.length; i++) {
            // Process file and add to attachments
            const fileUrl = fileUrls[i]
            const fileName = fileUrl.toString().split('/').pop()

            // Emit signal for Python to process the file
            fileRequested(fileUrl)

            // Add to model (Python will update with correct size/tokens later)
            fileAttachmentsModel.append({
                "fileName": fileName,
                "filePath": fileUrl,
                "fileSize": "Calculating...",
                "tokenCount": 0
            })
        }
    }

    // Add these functions to the MainWindow.qml file
    // Add them near the other utility functions

    // Update file info in the model
    function updateFileInfo(fileInfo) {
        // Find the file in the model
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            const item = fileAttachmentsModel.get(i)
            if (item.fileName === fileInfo.fileName ||
                item.filePath.toString().endsWith(fileInfo.fileName)) {

                // Update the item properties
                fileAttachmentsModel.set(i, {
                    "fileName": fileInfo.fileName,
                    "filePath": fileInfo.filePath,
                    "fileSize": fileInfo.fileSize,
                    "tokenCount": fileInfo.tokenCount
                })
                break
            }
        }
    }

    // Update file processing progress
    function updateFileProgress(fileName, progress) {
        // Find the file in the model
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            const item = fileAttachmentsModel.get(i)
            if (item.fileName === fileName ||
                item.filePath.toString().endsWith(fileName)) {

                // Update the file size to show progress
                fileAttachmentsModel.set(i, {
                    "fileSize": `Processing ${progress}%`
                })
                break
            }
        }
    }

    // Handle file processing errors
    function handleFileError(fileName, errorMessage) {
        console.error(`Error processing file ${fileName}: ${errorMessage}`)

        // Find the file in the model
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            const item = fileAttachmentsModel.get(i)
            if (item.fileName === fileName ||
                item.filePath.toString().endsWith(fileName)) {

                // Update the item to show error
                fileAttachmentsModel.set(i, {
                    "fileSize": "Error",
                    "tokenCount": 0
                })
                break
            }
        }

        // Show error message to user
        // You could implement a toast notification or error dialog here
    }

    // Add a function to handle errors from QML side
    function handleError(errorMsg) {
        console.error("QML Error: " + errorMsg)
        // Emit signal for Python to log
        errorOccurred(errorMsg)

        // Show error to user
        // You could add a toast notification or dialog here
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

    Connections {
        target: conversationViewModel
        enabled: conversationViewModel !== null && typeof conversationViewModel !== "undefined"

        function conversationLoaded(conversation) {
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

        function messageBranchChanged(branch) {
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

        function messageStreamChunk(chunk) {
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

        function tokenUsageUpdated(usage) {
            // Update token usage display
            let tokenText = "Tokens: " + usage.completion_tokens + " / " + usage.total_tokens

            // Add reasoning tokens if available
            if (usage.completion_tokens_details && usage.completion_tokens_details.reasoning_tokens) {
                tokenText += " (" + usage.completion_tokens_details.reasoning_tokens + " reasoning)"
            }

            tokenUsageText.text = tokenText
        }

        function loadingStateChanged(loading) {
            // Update loading state
            isLoading = loading
        }

        // Add any additional signal handlers here
        function messageAdded(message) {
            // This might be used to handle added messages separately
            // from the branch change
        }

        function reasoningStepsChanged(steps) {
            // Handle reasoning steps updates
        }

        function messagingComplete() {
            // Handle when messaging is complete
        }
    }
    property Timer debugTimer: Timer
    {
        interval: 500
        repeat: true
        running: true
        onTriggered: {
            if (typeof conversationViewModel !== "undefined" && conversationViewModel) {
                console.log("DEBUG: conversationViewModel is now available");
                debugTimer.running = false;
            } else {
                console.log("DEBUG: conversationViewModel is still undefined");
            }
        }
    }

    // Log property changes
    onConversationViewModelChanged: {
        console.log("DEBUG: conversationViewModel property changed:",
            conversationViewModel ? "defined" : "undefined");
    }

    // On application startup
    Component.onCompleted: {
        console.log("MainWindow initialization started");

        // Make sure the models are prepared
        conversationsModel.clear();
        messagesModel.clear();

        // Check if view models are ready
        if (typeof conversationViewModel === "undefined" || !conversationViewModel) {
            console.warn("conversationViewModel is not defined yet");
            // Start the init timer to retry later
            initTimer.start();
            return;
        }

        console.log("conversationViewModel is available, initializing app");

        // Initialize the application
        initializeApp();
    }

    // Add this Timer to the ApplicationWindow to handle delayed initialization
    Timer {
        id: initTimer
        interval: 1000 // Increased from 500ms to give more time
        repeat: false
        onTriggered: {
            console.log("Init timer triggered");
            if (typeof conversationViewModel !== "undefined" && conversationViewModel) {
                console.log("conversationViewModel now available, initializing");
                initializeApp();
            } else {
                console.error("conversationViewModel still not available after delay");
                errorDialog.title = "Connection Error";
                errorDialog.message = "Could not connect to application backend. Please restart the application.";
                errorDialog.open();
            }
        }
    }
}