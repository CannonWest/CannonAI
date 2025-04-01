// src/views/qml/MainWindow.qml
// Version: Fixed invalid 'shortcut' property on MenuItem

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs // Keep for FileDialog

import "./components" as Components

ApplicationWindow {
    id: mainWindow
    objectName: "mainWindow"
    visible: true
    width: 1200
    height: 800
    title: "CannonAI Chat Interface"

    // --- Theme Properties ---
    property color backgroundColor: "#2B2B2B"
    property color foregroundColor: "#F8F8F2"
    property color accentColor: "#6272A4"
    property color highlightColor: "#44475A"
    property color userMessageColor: "#50FA7B"
    property color assistantMessageColor: "#8BE9FD"
    property color systemMessageColor: "#FFB86C"
    property color errorColor: "#FF5555"

    // --- ViewModel References (Set by Python) ---
    property var conversationViewModel: null
    property var settingsViewModel: null

    // --- Application State (Driven by ViewModel Signals) ---
    property bool isLoading: false
    property var currentConversation: null
    property var currentBranch: []

    // --- Internal UI Models ---
    ListModel {
        id: conversationsModel
    }
    ListModel {
        id: messagesModel
    }
    ListModel {
        id: fileAttachmentsModel
    }

    // --- Signals to Python ---
    signal fileRequested(string filePath)

    signal errorOccurred(string errorMessage)

    signal cleanupRequested()

    // --- Initialization ---
    Component.onCompleted: {
        console.log("MainWindow: Component.onCompleted");
        conversationsModel.clear();
        messagesModel.clear();
        fileAttachmentsModel.clear();
        initializeApp();
    }

    function initializeApp() {
        if (!conversationViewModel) {
            console.error("initializeApp: conversationViewModel is not available!");
            errorDialog.title = "Initialization Error";
            errorDialog.text = "Critical component (conversationViewModel) missing. Application cannot function.";
            errorDialog.open();
            return;
        }
        console.log("QML: Requesting initial conversation list load.");
        conversationViewModel.load_all_conversations_threaded();
    }

    // --- Window Closing Handler ---
    onClosing: function (close) {
        console.log("MainWindow: Window closing event received");
        close.accepted = false;
        cleanupRequested();
    }

    // --- Menu Bar (Shortcuts Corrected) ---
    menuBar: MenuBar {
        Menu {
            title: "File"
            MenuItem {
                id: newConvMenuItem // Give IDs if needed for shortcuts
                text: "New Conversation"
                enabled: conversationViewModel !== null
                onTriggered: { if (conversationViewModel) conversationViewModel.create_new_conversation("New Conversation"); }
                // Add Shortcut element inside or associated
                Shortcut {
                    sequence: "Ctrl+N"; onActivated: newConvMenuItem.trigger()
                }
            }
            MenuItem {
                id: saveConfMenuItem
                text: "Save Confirmation"
                onTriggered: saveDialog.open()
                Shortcut {
                    sequence: "Ctrl+S"; onActivated: saveConfMenuItem.trigger()
                }
            }
            MenuSeparator {
            }
            MenuItem {
                id: exitMenuItem
                text: "Exit"
                onTriggered: mainWindow.close()
                Shortcut {
                    sequence: "Ctrl+Q"; onActivated: exitMenuItem.trigger()
                }
            }
        }
        Menu {
            title: "Edit"
            MenuItem {
                id: renameMenuItem
                text: "Rename Conversation"
                enabled: conversationList.currentIndex >= 0
                onTriggered: renameDialog.open()
                Shortcut {
                    sequence: "F2"; onActivated: renameMenuItem.trigger()
                }
            }
            MenuItem {
                id: duplicateMenuItem
                text: "Duplicate Conversation"
                enabled: conversationList.currentIndex >= 0 && conversationViewModel !== null
                onTriggered: duplicateConversation()
                Shortcut {
                    sequence: "Ctrl+D"; onActivated: duplicateMenuItem.trigger()
                }
            }
            MenuItem {
                id: searchMenuItem
                text: "Search Messages"
                enabled: conversationViewModel !== null
                onTriggered: {
                    const currentConvId = currentConversation ? currentConversation.id : null;
                    searchDialog.initialize(currentConvId);
                    searchDialog.open();
                }
                Shortcut {
                    sequence: "Ctrl+F"; onActivated: searchMenuItem.trigger()
                }
            }
        }
        Menu {
            title: "Settings"
            MenuItem {
                id: settingsMenuItem
                text: "API Settings"
                enabled: settingsViewModel !== null
                onTriggered: openSettingsDialog()
                // Optional: Add shortcut like Ctrl+,
                // Shortcut { sequence: "Ctrl+,"; onActivated: settingsMenuItem.trigger() }
            }
        }
        Menu {
            title: "Help"
            MenuItem {
                text: "About"
                onTriggered: aboutDialog.open()
            }
        }
    } // End MenuBar

    // --- Main Content Area (SplitView) ---
    SplitView {
        id: mainSplitView
        anchors.fill: parent
        orientation: Qt.Horizontal

        // === Sidebar ===
        Rectangle {
            id: sidebarContainer
            SplitView.preferredWidth: 250; SplitView.minimumWidth: 180
            color: highlightColor

            ColumnLayout {
                anchors.fill: parent; spacing: 8

                // Sidebar Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 40
                    color: accentColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8

                        Label { // Use Label for better alignment control
                            text: "Conversations"
                            color: foregroundColor
                            font.pixelSize: 16
                            font.bold: true
                            verticalAlignment: Text.AlignVCenter
                            Layout.fillWidth: true
                        }

                        Button {
                            text: "+"
                            ToolTip.text: "New Conversation (Ctrl+N)"
                            ToolTip.visible: hovered
                            ToolTip.delay: 500
                            enabled: conversationViewModel !== null
                            onClicked: {
                                if (conversationViewModel) {
                                    conversationViewModel.create_new_conversation("New Conversation");
                                }
                            }
                            background: Rectangle {
                                color: highlightColor; radius: 4
                            }
                            contentItem: Text {
                                text: parent.text; color: foregroundColor; font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // Conversation List
                ListView {
                    id: conversationList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: conversationsModel // Use the internal ListModel

                    delegate: Components.ConversationItem
                    {
                        width: conversationList.width // Ensure delegate fills width
                        // Connect signals to slot methods
                        onItemClicked: {
                            if (conversationList.currentIndex !== index && conversationViewModel) {
                                console.log("QML: Conversation item clicked:", model.id);
                                conversationList.currentIndex = index; // Update selection immediately
                                conversationViewModel.load_conversation(model.id);
                            }
                        }
                        onItemRightClicked: {
                            conversationList.currentIndex = index; // Select before showing menu
                            contextMenu.popup();
                        }
                        onItemDoubleClicked: {
                            conversationList.currentIndex = index;
                            renameDialog.open(); // Open rename dialog
                        }
                    }

                    // Context Menu
                    Menu {
                        id: contextMenu
                        MenuItem {
                            text: "Rename"; onClicked: renameDialog.open()
                        }
                        MenuItem {
                            text: "Duplicate"; onClicked: duplicateConversation()
                        } // TODO: Implement duplicate_conversation
                        MenuItem {
                            text: "Delete"; onClicked: deleteConfirmDialog.open()
                        }
                    }
                }
            }
        } // End Sidebar

        Rectangle {
            id: chatContainer
            SplitView.fillWidth: true
            color: backgroundColor

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 8; spacing: 8

                // Branch Navigation Bar (Dynamically populated)
                Rectangle {
                    id: branchNavBar
                    Layout.fillWidth: true
                    height: 50
                    color: highlightColor
                    radius: 4
                    visible: currentBranch.length > 1 // Show only if there's history

                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 4
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded // Show scrollbar only if needed
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

                        Row {
                            id: branchNavRow // Buttons added by updateBranchNavigation()
                            spacing: 8
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // Chat Messages Area
                ScrollView {
                    id: messagesScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true // Takes up most vertical space
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOn

                    ListView {
                        id: messagesView
                        anchors.fill: parent
                        anchors.margins: 8 // Padding inside the scroll view
                        spacing: 16 // Spacing between messages
                        verticalLayoutDirection: ListView.BottomToTop // New messages appear at bottom
                        model: messagesModel // Use internal ListModel

                        delegate: Components.MessageDelegate
                        {
                        } // Custom delegate handles rendering

                        // Auto-scroll to bottom (slightly adjusted logic for BottomToTop)
                        onContentHeightChanged: positionViewAtBeginning() // Keep newest message visible
                        Component.onCompleted: positionViewAtBeginning() // Scroll on initial load
                    }
                }

                // Thinking/Loading Indicator
                Rectangle {
                    id: thinkingIndicator
                    Layout.fillWidth: true
                    height: visible ? 30 : 0 // Collapse when not visible
                    color: highlightColor
                    radius: 4
                    visible: isLoading // Bound to ViewModel state
                    Behavior on height {
                        NumberAnimation {
                            duration: 150
                        }
                    } // Animate collapse/expand

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8
                        visible: parent.visible // Hide content when collapsed

                        BusyIndicator {
                            width: 20; height: 20
                            running: thinkingIndicator.visible
                        }
                        Label { // Use Label
                            text: "Thinking..."
                            color: foregroundColor
                            Layout.fillWidth: true
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }

                // File Attachments Staging Area
                Rectangle {
                    id: attachmentsArea
                    Layout.fillWidth: true
                    height: visible ? 60 : 0 // Collapse when empty
                    color: highlightColor
                    radius: 4
                    visible: fileAttachmentsModel.count > 0 // Show only if files are attached
                    Behavior on height {
                        NumberAnimation {
                            duration: 150
                        }
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4
                        visible: parent.visible

                        RowLayout {
                            Layout.fillWidth: true
                            Label { // Use Label
                                text: "Attachments: " + fileAttachmentsModel.count
                                color: foregroundColor; Layout.fillWidth: true
                                verticalAlignment: Text.AlignVCenter
                            }
                            Button {
                                text: "Clear All"; onClicked: fileAttachmentsModel.clear()
                                background: Rectangle {
                                    color: highlightColor; radius: 4; border.color: accentColor; border.width: 1
                                }
                                contentItem: Text {
                                    text: parent.text; color: foregroundColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        ListView { // Horizontal list of attached files
                            id: attachmentsView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            orientation: ListView.Horizontal
                            spacing: 8
                            model: fileAttachmentsModel

                            delegate: Rectangle { // Simple delegate for attached file
                                width: 150; height: attachmentsView.height
                                color: accentColor; radius: 4

                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 4; spacing: 4

                                    Label { // Use Label
                                        text: model.fileName // Display filename
                                        color: foregroundColor; elide: Text.ElideRight
                                        Layout.fillWidth: true
                                        verticalAlignment: Text.AlignVCenter
                                        ToolTip.text: model.fileName + "\n" + model.fileSize // Show full name/size on hover
                                        ToolTip.visible: hovered
                                    }
                                    Button { // Remove button
                                        text: "×"; width: 20; height: 20
                                        onClicked: fileAttachmentsModel.remove(index)
                                        background: Rectangle {
                                            color: highlightColor; radius: 2
                                        }
                                        contentItem: Text {
                                            text: "×"; color: foregroundColor; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Input Area
                Rectangle {
                    id: inputArea
                    Layout.fillWidth: true
                    // Dynamic height based on content, with min/max
                    height: Math.min(Math.max(inputField.implicitHeight + 20, 80), 200)
                    color: highlightColor
                    radius: 4

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 8

                        TextArea { // Use TextArea for better multiline handling
                            id: inputField
                            Layout.fillWidth: true
                            Layout.fillHeight: true // Fill available height
                            placeholderText: "Type your message (Shift+Enter for newline)..."
                            color: foregroundColor
                            background: Rectangle {
                                color: "transparent"
                            } // No background needed
                            wrapMode: TextEdit.Wrap // Enable wrapping
                            font.pixelSize: 14
                            enabled: !isLoading // Disable input while loading

                            // Handle Enter/Shift+Enter keys
                            Keys.onPressed: (event) => {
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    if (event.modifiers & Qt.ShiftModifier) {
                                        // Allow default behavior (insert newline)
                                        event.accepted = false;
                                    } else {
                                        // Send message
                                        sendMessage();
                                        event.accepted = true; // Consume the event
                                    }
                                } else {
                                    event.accepted = false; // Allow other keys
                                }
                            }
                        }

                        // Action Buttons Column
                        ColumnLayout {
                            Layout.preferredWidth: 40 // Fixed width for buttons column
                            spacing: 8

                            Button { // Send Button
                                id: sendButton
                                text: "➤" // Use an icon/symbol
                                ToolTip.text: "Send Message (Enter)"
                                ToolTip.visible: hovered
                                Layout.fillWidth: true // Use full column width
                                Layout.preferredHeight: 40
                                enabled: !isLoading && inputField.text.trim() !== ""
                                onClicked: sendMessage()
                                background: Rectangle {
                                    color: sendButton.enabled ? accentColor : Qt.rgba(0.27, 0.28, 0.35, 0.5); radius: 4
                                }
                                contentItem: Text {
                                    text: parent.text; color: foregroundColor; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Button { // Retry Button
                                id: retryButton
                                text: "↺"
                                ToolTip.text: "Retry Last Response"
                                ToolTip.visible: hovered
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                enabled: !isLoading && messagesModel.count > 0 && currentBranch.length > 0 && currentBranch[currentBranch.length - 1].role === 'assistant' // Enable only if last msg is assistant
                                onClicked: { if (conversationViewModel) conversationViewModel.retry_last_response(); } // TODO: Implement retry_last_response
                                background: Rectangle {
                                    color: retryButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5); radius: 4; border.color: accentColor; border.width: 1
                                }
                                contentItem: Text {
                                    text: "↺"; color: foregroundColor; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Button { // Attach Button
                                id: attachButton
                                text: "📎"
                                ToolTip.text: "Attach File"
                                ToolTip.visible: hovered
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                enabled: !isLoading
                                onClicked: fileDialog.open() // Open file dialog
                                background: Rectangle {
                                    color: attachButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5); radius: 4; border.color: accentColor; border.width: 1
                                }
                                contentItem: Text {
                                    text: "📎"; color: foregroundColor; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }
                    }
                }

                // Status Bar (Tokens, Model)
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

                        Label { // Use Label
                            id: tokenUsageText
                            text: "Tokens: N/A" // Updated by signal
                            color: foregroundColor; opacity: 0.8
                            Layout.fillWidth: true
                            verticalAlignment: Text.AlignVCenter
                        }
                        Label { // Use Label
                            id: modelInfoText
                            text: "Model: " + (currentSettings.model || "N/A") // Show current setting
                            color: foregroundColor; opacity: 0.8
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                            verticalAlignment: Text.AlignVCenter
                            // TODO: Update this dynamically if model changes during conversation
                            // Needs signal from ViewModel if model can change per-message
                        }
                    }
                }
            } // End Main Chat Area ColumnLayout
        } // End Main Chat Area Rectangle
    } // End SplitView

    // --- Dialogs ---
    // File Dialog for Attachments
    FileDialog {
        id: fileDialog
        title: "Attach File(s)"
        fileMode: FileDialog.OpenFiles // Allow multiple files
        onAccepted: {
            // Iterate through selected files and signal Python for each
            for (var i = 0; i < selectedFiles.length; i++) {
                handleFileSelected(selectedFiles[i]);
            }
        }
    }

    // Simple Confirmation/Error Dialogs
    Dialog {
        id: saveDialog
        title: "Save Conversations"; standardButtons: Dialog.Ok; modal: true
        width: 350; // Explicit width
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        contentItem: Label {
            text: "Conversations are saved automatically."; color: foregroundColor; padding: 16; wrapMode: Text.WordWrap
        }
    }

    Dialog {
        id: errorDialog // General error display
        title: "Error"; standardButtons: Dialog.Ok; modal: true
        width: 400; property string text: "" // Use 'text' property
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: errorColor; border.width: 1
        }
        contentItem: Label {
            text: errorDialog.text; color: foregroundColor; padding: 16; wrapMode: Text.WordWrap
        }
    }

    Dialog {
        id: renameDialog
        title: "Rename Conversation"; standardButtons: Dialog.Ok | Dialog.Cancel; modal: true
        width: 400; // Fixed width
        // Remove height binding causing loop: height: contentColumn.implicitHeight + 60
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        onAccepted: {
            if (conversationList.currentIndex >= 0 && conversationViewModel) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id;
                conversationViewModel.rename_conversation(conversationId, renameField.text);
            }
        }
        contentItem: ColumnLayout { // Use ColumnLayout for content
            id: contentColumn
            width: renameDialog.width - 32 // Adjust width based on dialog width
            spacing: 16
            Label {
                text: "Enter new conversation name:"; color: foregroundColor; Layout.fillWidth: true
            }
            TextField {
                id: renameField; Layout.fillWidth: true; color: foregroundColor
                background: Rectangle {
                    color: highlightColor; radius: 4
                }
                // Populate with current name when dialog opens
                Component.onCompleted: { if (conversationList.currentIndex >= 0) text = conversationsModel.get(conversationList.currentIndex).name; }
                onAccepted: renameDialog.accept() // Accept on Enter key
            }
        }
        // Adjust dialog height dynamically after content is ready
        Component.onCompleted: height = contentColumn.implicitHeight + 80 // Add padding/button space
        // Re-populate field when dialog is opened
        onOpened: { if (conversationList.currentIndex >= 0) renameField.text = conversationsModel.get(conversationList.currentIndex).name; }

    }

    Dialog {
        id: aboutDialog
        title: "About CannonAI"; standardButtons: Dialog.Close; modal: true
        width: 400
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        contentItem: ColumnLayout {
            width: parent.width - 32; spacing: 16
            Label {
                text: "CannonAI Chat Interface"; color: foregroundColor; font.bold: true; font.pixelSize: 16
            }
            Label {
                text: "A desktop application using PyQt6 and MVVM for interacting with AI models.\n\nVersion: 1.0.0 (Placeholder)"
                color: foregroundColor; wrapMode: Text.WordWrap
            }
        }
        Component.onCompleted: height = contentItem.implicitHeight + 80
    }

    Dialog {
        id: deleteConfirmDialog
        title: "Delete Conversation"; standardButtons: Dialog.Yes | Dialog.No; modal: true
        width: 400
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        onAccepted: { // Triggered only if "Yes" is clicked
            if (conversationList.currentIndex >= 0 && conversationViewModel) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id;
                conversationViewModel.delete_conversation(conversationId);
            }
        }
        contentItem: Label {
            text: "Are you sure you want to delete this conversation? This action cannot be undone."; color: foregroundColor; wrapMode: Text.WordWrap; padding: 16
        }
        Component.onCompleted: height = contentItem.implicitHeight + 80
    }

    // --- Custom Component Dialogs ---
    // Settings Dialog
    Components.SettingsDialog {
        id: settingsDialog
        // Set initial size hints if needed
        // width: 600; height: 700
        // Connect signals
        onSettingsSaved: (settings) => {
            if (settingsViewModel) settingsViewModel.update_settings(settings);
        }
        // Make sure the dialog uses colors defined in MainWindow
        // backgroundColor: mainWindow.backgroundColor
        // foregroundColor: mainWindow.foregroundColor
        // accentColor: mainWindow.accentColor
        // highlightColor: mainWindow.highlightColor
    }

    // Search Dialog
    Components.SearchDialog {
        id: searchDialog
        // width: 500; height: 400
        // TODO: Connect SearchDialog signals/actions to ConversationViewModel
        // Example: onSearchRequested: (term, searchAll) => { conversationViewModel.search_conversations(...) }
        // Example: onResultSelected: (convId, msgId) => { conversationViewModel.load_conversation(convId); conversationViewModel.navigate_to_message(msgId); }
        // Pass theme colors
        // backgroundColor: mainWindow.backgroundColor
        // foregroundColor: mainWindow.foregroundColor
        // accentColor: mainWindow.accentColor
        // highlightColor: mainWindow.highlightColor
    }

    // --- Utility Functions ---
    // Function to handle file attachments (called by FileDialog)
    function handleFileSelected(fileUrl) {
        if (!bridge) {
            console.error("QML: Bridge is not available for file path conversion.");
            return;
        }
        const filePath = bridge.fileUrlToPath(fileUrl); // Convert URL to path using bridge
        console.log("QML: File selected:", filePath);
        fileRequested(filePath); // Signal Python with the actual file path

        const fileName = fileUrl.toString().split('/').pop();
        fileAttachmentsModel.append({
            "fileName": fileName,
            "filePath": filePath, // Store path for potential use
            "fileSize": "Pending...",
            "tokenCount": 0,
            "status": "pending"
        });
    }

    // Function to send message (called by button/Enter key)
    function sendMessage() {
        if (!conversationViewModel || !currentConversation) {
            console.error("Cannot send message: ViewModel or conversation not ready.");
            errorDialog.text = "Please select or create a conversation first.";
            errorDialog.open();
            return;
        }
        if (inputField.text.trim() === "") return; // Don't send empty messages

        // Prepare attachments data from the staging model
        let attachmentsData = [];
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            const item = fileAttachmentsModel.get(i);
            attachmentsData.push({
                fileName: item.fileName,
                filePath: item.filePath // Send the path obtained earlier
            });
        }

        console.log("QML: Sending message in conversation:", currentConversation.id);
        conversationViewModel.send_message(currentConversation.id, inputField.text, attachmentsData);

        inputField.text = ""; // Clear input field
        fileAttachmentsModel.clear(); // Clear staged attachments
    }

    // Function to trigger conversation duplication
    function duplicateConversation() {
        if (!conversationViewModel || !currentConversation) return;
        console.log("QML: Requesting duplication of conversation:", currentConversation.id);
        // TODO: Implement duplicate_conversation in ViewModel if needed
        // conversationViewModel.duplicate_conversation(currentConversation.id, currentConversation.name + " (Copy)");
        console.warn("QML: Duplicate conversation functionality not yet implemented in ViewModel.");
    }

    // Function to open settings dialog
    function openSettingsDialog() {
        if (!settingsViewModel) {
            console.error("QML: settingsViewModel not available.");
            errorDialog.text = "Settings module is not available.";
            errorDialog.open();
            return;
        }
        // Pass current settings from ViewModel to dialog for initialization
        settingsDialog.initialize(settingsViewModel.get_settings());
        settingsDialog.open();
    }

    // Function to update branch navigation UI
    function updateBranchNavigation(branch) {
        branchNavRow.children = []; // Clear existing buttons
        if (!branch || branch.length <= 1) {
            branchNavBar.visible = false; // Hide if only one or zero messages
            return;
        }
        branchNavBar.visible = true;

        for (let i = 0; i < branch.length; i++) {
            const node = branch[i];
            // Skip system messages unless it's the very first one
            if (node.role === "system" && i > 0) continue;

            let buttonText = "";
            if (node.role === "user") buttonText = "👤 User";
            else if (node.role === "assistant") buttonText = "🤖 Asst"; // Shorter text
            else buttonText = "🔧 Sys";

            // Create navigation button dynamically
            const button = Qt.createQmlObject(
                'import QtQuick.Controls 2.15; Button { \
                    text: qsTr("' + buttonText + '"); \
                    property string nodeId: "' + node.id + '"; \
                    flat: true; /* Less prominent look */ \
                    background: Rectangle { color: "transparent" } \
                    contentItem: Text { \
                        text: parent.text; \
                        color: ' + (i === branch.length - 1 ? 'accentColor' : 'foregroundColor') + '; \
                        font.bold: ' + (i === branch.length - 1) + '; \
                        opacity: ' + (i === branch.length - 1 ? 1.0 : 0.7) + '; \
                    } \
                    onClicked: { \
                        if (conversationViewModel && nodeId !== currentBranch[currentBranch.length-1].id) { \
                            console.log("QML: Navigating to message:", nodeId); \
                            conversationViewModel.navigate_to_message(nodeId); \
                        } \
                    } \
                }',
                branchNavRow, // Parent item
                "navButton_" + i // Unique object name
            );

            // Add arrow separator if not the last visible item
            // Need to look ahead to see if the next item is system
            let nextVisibleIndex = -1;
            for (let j = i + 1; j < branch.length; j++) {
                if (branch[j].role !== "system") {
                    nextVisibleIndex = j;
                    break;
                }
            }
            if (nextVisibleIndex !== -1 && nextVisibleIndex < branch.length) {
                Qt.createQmlObject(
                    'import QtQuick 2.15; Text { text: "→"; color: foregroundColor; opacity: 0.5; anchors.verticalCenter: parent.verticalCenter }',
                    branchNavRow, "arrow_" + i
                );
            }
        }
    }

    // --- ViewModel Signal Connections ---
    Connections {
        target: conversationViewModel
        enabled: conversationViewModel !== null // Activate connections only when VM is set

        function onConversationListUpdated(convList) {
            console.log("QML: Received conversationListUpdated signal with", convList ? convList.length : 0, "items.");
            if (!convList) return;
            conversationsModel.clear();
            for (let i = 0; i < convList.length; i++) conversationsModel.append(convList[i]);

            if (convList.length > 0 && conversationList.currentIndex === -1) {
                console.log("QML: Auto-selecting first conversation:", convList[0].id);
                conversationList.currentIndex = 0;
                // ViewModel should handle loading the first conversation after list update
            } else if (convList.length === 0) {
                messagesModel.clear();
                currentConversation = null;
                updateBranchNavigation([]); // Clear branch nav
            }
        }

        function onConversationLoaded(conversation) {
            console.log("QML: Received conversationLoaded signal for:", conversation ? conversation.id : "null");
            if (!conversation) return;
            currentConversation = conversation; // Update current conversation state

            // Ensure list selection matches loaded conversation
            for (let i = 0; i < conversationsModel.count; i++) {
                if (conversationsModel.get(i).id === conversation.id) {
                    if (conversationList.currentIndex !== i) conversationList.currentIndex = i;
                    // Update list item data if necessary (name might have changed)
                    conversationsModel.setProperty(i, "name", conversation.name);
                    conversationsModel.setProperty(i, "modified_at", conversation.modified_at);
                    break;
                }
            }
            // ViewModel should trigger branch loading via its own logic after load completes
        }

        function onMessageBranchChanged(branch) {
            console.log("QML: Received messageBranchChanged signal with", branch.length, "messages.");
            currentBranch = branch; // Update state
            messagesModel.clear();
            let isStreamingPlaceholder = false;
            for (let i = 0; i < branch.length; i++) {
                const node = branch[i];
                messagesModel.append({
                    id: node.id, role: node.role, content: node.content,
                    timestamp: node.timestamp,
                    // Ensure attachments is always an array for the delegate
                    attachments: node.file_attachments ? node.file_attachments : []
                });
                if (i === branch.length - 1 && node.role === 'assistant' && node.id && node.id.startsWith('temp-')) {
                    isStreamingPlaceholder = true;
                }
            }
            updateBranchNavigation(branch);
            // Use timer to ensure layout is updated before scrolling
            Qt.callLater(messagesView.positionViewAtBeginning);
        }

        function onMessageStreamChunk(chunk) {
            if (messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1;
                let lastMessage = messagesModel.get(lastIndex);
                if (lastMessage.role === "assistant") {
                    messagesModel.setProperty(lastIndex, "content", lastMessage.content + chunk);
                } else { // Add new temporary assistant message
                    messagesModel.append({id: "temp-" + Date.now(), role: "assistant", content: chunk, timestamp: new Date().toISOString(), attachments: []});
                }
                Qt.callLater(messagesView.positionViewAtBeginning); // Scroll during stream
            } else { // First message is streaming
                messagesModel.append({id: "temp-" + Date.now(), role: "assistant", content: chunk, timestamp: new Date().toISOString(), attachments: []});
                Qt.callLater(messagesView.positionViewAtBeginning);
            }
        }

        function onMessageAdded(message) {
            console.log("QML: Received messageAdded signal for:", message.id, "Role:", message.role);
            // If the last message was temporary, replace it fully
            if (message.role === 'assistant' && messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1;
                let lastMessage = messagesModel.get(lastIndex);
                if (lastMessage.id.startsWith("temp-")) {
                    console.log("QML: Replacing temporary streaming message with final:", message.id);
                    // Use setProperty for individual fields to avoid recreating the whole item
                    messagesModel.setProperty(lastIndex, "id", message.id);
                    messagesModel.setProperty(lastIndex, "content", message.content);
                    messagesModel.setProperty(lastIndex, "timestamp", message.timestamp);
                    messagesModel.setProperty(lastIndex, "attachments", message.file_attachments || []);
                } else if (lastMessage.id !== message.id) {
                    // This case should be rare if branchChanged handles additions correctly
                    // console.warn("QML: messageAdded received but last message wasn't temporary. Appending.")
                    // messagesModel.append({...}); // Append if absolutely necessary
                }
            }
            Qt.callLater(messagesView.positionViewAtBeginning);
        }

        function onTokenUsageUpdated(usage) {
            let tokenText = "Tokens: ";
            tokenText += (usage && usage.completion_tokens !== undefined && usage.total_tokens !== undefined)
                ? `${usage.completion_tokens} / ${usage.total_tokens}` : "N/A";
            tokenUsageText.text = tokenText;
        }

        function onLoadingStateChanged(loading) {
            console.log("QML: Received loadingStateChanged signal:", loading);
            isLoading = loading;
        }

        function onErrorOccurred(errorMessage) {
            console.error("QML: Received errorOccurred signal from ViewModel:", errorMessage);
            errorDialog.title = "Application Error";
            errorDialog.text = errorMessage;
            errorDialog.open();
        }

        function onReasoningStepsChanged(steps) {
            console.log("QML: Received reasoningStepsChanged signal with", steps.length, "steps.");
            // TODO: Display reasoning steps (e.g., in a separate panel or tooltip)
        }

        function onMessagingComplete() {
            console.log("QML: Received messagingComplete signal.");
            // Finalize UI state, e.g., ensure input is enabled if it wasn't already
            // inputField.enabled = !isLoading; // isLoading should already be false
        }
    } // End Connections for conversationViewModel

    Connections {
        target: settingsViewModel
        enabled: settingsViewModel !== null

        // Example: Update model info text if settings change
        function onSettingChanged(key, value) {
            if (key === "model") {
                modelInfoText.text = "Model: " + (value || "N/A");
            }
        }

        function onSettingsChanged(settings) {
            if (settings && settings.model) {
                modelInfoText.text = "Model: " + settings.model;
            }
            // Update any other relevant UI based on settings changes
        }
    } // End Connections for settingsViewModel

} // End ApplicationWindow