// src/views/qml/MainWindow.qml
// Version: Integrated SearchDialog signals & Duplicate Conversation call

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

    // --- App Controller Reference (Set by Python) ---
    property var appController: null // Expects the Python ApplicationController instance

    // --- Application State (Driven by ViewModel Signals) ---
    property bool isLoading: false // Global loading state (used by thinking indicator)
    property var currentConversation: null // Holds the fully loaded Conversation object/dict
    property var currentBranch: [] // Holds the list of Message objects/dicts for the current view

    // --- Internal UI Models ---
    ListModel {
        id: conversationsModel // For the sidebar list
    }
    ListModel {
        id: messagesModel // For the main chat message view
    }
    ListModel {
        id: fileAttachmentsModel // For the staging area before sending
    }

    // --- Signals to Python ---
    signal fileRequested(string filePath) // When user selects a file to attach
    signal errorOccurred(string errorMessage) // For generic QML-side errors (less used now)
    signal cleanupRequested() // When window is closing

    // --- Initialization ---
    Component.onCompleted: {
        console.log("QML: MainWindow Component.onCompleted - QML structure loaded.");
        // DO NOT call initializeApp() here anymore.
        conversationsModel.clear();
        messagesModel.clear();
        fileAttachmentsModel.clear();
        // Check appController availability early (might still be null here, but check later too)
        // console.log("QML: appController in onCompleted:", appController);
    }

    // --- Connections to Python Controller ---
    Connections {
        target: appController // Target the controller instance set from Python
        enabled: appController !== null // Only connect if the controller exists

        // Function name MUST match the signal name from Python (initializationComplete)
        function onInitializationComplete() {
            // <<< ADD QML LOGGING >>>
            console.log("QML: >>> Received onInitializationComplete signal.");
            console.log("QML: Checking appController:", appController); // Verify controller object
            console.log("QML: Checking conversationViewModel:", conversationViewModel); // Verify VM object

            // Now it's safe to initialize QML logic that depends on ViewModels
            initializeApp();
            // <<< ADD QML LOGGING >>>
            console.log("QML: <<< Exited onInitializationComplete handler.");
        }
    }

    // --- QML Initialization Function (Called by Signal Handler) ---
    function initializeApp() {
        // <<< ADD QML LOGGING >>>
        console.log("QML: >>> initializeApp() called.");
        // Check if the conversationViewModel context property is actually available
        if (!conversationViewModel) {
            console.error("QML: initializeApp FATAL: conversationViewModel is null! Cannot load initial data.");
            errorDialog.title = "Initialization Error";
            errorDialog.text = "Critical component (conversationViewModel) missing. Application cannot function.";
            errorDialog.open();
            return;
        }

        // If the ViewModel exists, trigger the initial load via its slot
        console.log("QML: conversationViewModel found. Attempting to call load_all_conversations_threaded()...");
        try {
            conversationViewModel.load_all_conversations_threaded(); // <<< CALL REMAINS HERE
            console.log("QML: Call to load_all_conversations_threaded() completed without JS error.");
        } catch (e) {
            // Catch potential JavaScript errors during the call itself
            console.error("QML: *** JavaScript Error calling load_all_conversations_threaded():", e);
            errorDialog.title = "QML Error";
            errorDialog.text = "Failed to call initial load function: " + e;
            errorDialog.open();
        }
        // <<< ADD QML LOGGING >>>
        console.log("QML: <<< initializeApp() finished.");
    }

    // --- Window Closing Handler ---
    onClosing: function (close) {
        console.log("MainWindow: Window closing event received");
        // Don't close immediately, signal Python to clean up first
        close.accepted = false;
        cleanupRequested();
        // Python side (_on_about_to_quit) will eventually call app.quit() after cleanup
    }

    // --- Menu Bar ---
    menuBar: MenuBar {
        Menu {
            title: "File"
            MenuItem {
                id: newConvMenuItem
                text: "New Conversation"
                enabled: conversationViewModel !== null && !isLoading
                onTriggered: { if (conversationViewModel) conversationViewModel.create_new_conversation("New Conversation"); }
                Shortcut {
                    sequence: "Ctrl+N"
                    // Call the action directly instead of trying to trigger the MenuItem
                    onActivated: { if (conversationViewModel && !isLoading) conversationViewModel.create_new_conversation("New Conversation"); }
                }
            }

            MenuItem {
                id: saveConfMenuItem
                text: "Save Confirmation"
                onTriggered: saveDialog.open()
                Shortcut {
                    sequence: "Ctrl+S"
                    onActivated: saveDialog.open()
                }
            }
            MenuSeparator {
            }
            MenuItem {
                id: exitMenuItem
                text: "Exit"
                onTriggered: mainWindow.close() // Triggers onClosing handler
                Shortcut {
                    sequence: "Ctrl+Q"
                    onActivated: mainWindow.close()
                }
            }
        }
        Menu {
            title: "Edit"
            MenuItem {
                id: renameMenuItem
                text: "Rename Conversation"
                enabled: conversationList.currentIndex >= 0 && !isLoading
                onTriggered: renameDialog.open()
                Shortcut {
                    sequence: "F2"
                    onActivated: { if (conversationList.currentIndex >= 0 && !isLoading) renameDialog.open(); }
                }
            }
            MenuItem {
                id: duplicateMenuItem
                text: "Duplicate Conversation"
                enabled: conversationList.currentIndex >= 0 && conversationViewModel !== null && !isLoading
                onTriggered: duplicateConversation() // Calls updated QML function
                Shortcut {
                    sequence: "Ctrl+D"
                    onActivated: { if (conversationList.currentIndex >= 0 && conversationViewModel !== null && !isLoading) duplicateConversation(); }
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
                    sequence: "Ctrl+F"
                    onActivated: {
                        if (conversationViewModel !== null) {
                            const currentConvId = currentConversation ? currentConversation.id : null;
                            searchDialog.initialize(currentConvId);
                            searchDialog.open();
                        }
                    }
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
                // Shortcut { sequence: "Ctrl+,"; onActivated: settingsMenuItem.trigger() } // Optional
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

                        Label {
                            text: "Conversations"
                            color: foregroundColor
                            font.pixelSize: 16; font.bold: true
                            verticalAlignment: Text.AlignVCenter
                            Layout.fillWidth: true
                        }
                        Button {
                            text: "+"; ToolTip.text: "New Conversation (Ctrl+N)"; ToolTip.visible: hovered; ToolTip.delay: 500
                            enabled: conversationViewModel !== null && !isLoading
                            onClicked: { if (conversationViewModel) conversationViewModel.create_new_conversation("New Conversation"); }
                            background: Rectangle {
                                color: highlightColor; radius: 4
                            }
                            contentItem: Text {
                                text: parent.text; color: foregroundColor; font.bold: true; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // Conversation List
                ListView {
                    id: conversationList
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    model: conversationsModel // Use the internal ListModel

                    delegate: Components.ConversationItem
                    {
                        width: conversationList.width
                        // Pass theme colors if needed by delegate
                        // foregroundColor: mainWindow.foregroundColor
                        // accentColor: mainWindow.accentColor

                        // Connect signals to slot methods
                        onItemClicked: {
                            if (conversationList.currentIndex !== index && conversationViewModel && !isLoading) {
                                console.log("QML: Conversation item clicked:", model.id);
                                conversationList.currentIndex = index; // Update selection immediately
                                conversationViewModel.load_conversation(model.id); // Trigger VM load
                            }
                        }
                        onItemRightClicked: {
                            conversationList.currentIndex = index; // Select before showing menu
                            contextMenu.popup();
                        }
                        onItemDoubleClicked: {
                            if (!isLoading) {
                                conversationList.currentIndex = index;
                                renameDialog.open(); // Open rename dialog
                            }
                        }
                    }

                    // Context Menu
                    Menu {
                        id: contextMenu
                        MenuItem {
                            text: "Rename"; onClicked: renameDialog.open(); enabled: !isLoading
                        }
                        MenuItem {
                            text: "Duplicate"; onClicked: duplicateConversation(); enabled: !isLoading
                        }
                        MenuItem {
                            text: "Delete"; onClicked: deleteConfirmDialog.open(); enabled: !isLoading
                        }
                    }
                } // End ListView
            } // End Sidebar ColumnLayout
        } // End Sidebar Rectangle

        // === Main Chat Area ===
        Rectangle {
            id: chatContainer
            SplitView.fillWidth: true
            color: backgroundColor

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 8; spacing: 8

                // Branch Navigation Bar
                Rectangle {
                    id: branchNavBar
                    Layout.fillWidth: true
                    height: 50
                    color: highlightColor
                    radius: 4
                    visible: currentBranch.length > 1 // Show only if there's history

                    ScrollView {
                        anchors.fill: parent; anchors.margins: 4
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff

                        Row {
                            id: branchNavRow
                            spacing: 8
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                } // End BranchNavBar

                // Chat Messages Area
                ScrollView {
                    id: messagesScroll
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOn

                    ListView {
                        id: messagesView
                        anchors.fill: parent; anchors.margins: 8
                        spacing: 16
                        verticalLayoutDirection: ListView.BottomToTop
                        model: messagesModel // Use internal ListModel

                        delegate: Components.MessageDelegate
                        {
                            // Pass theme colors if needed by delegate
                            // userMessageColor: mainWindow.userMessageColor
                            // assistantMessageColor: mainWindow.assistantMessageColor
                            // systemMessageColor: mainWindow.systemMessageColor
                            // foregroundColor: mainWindow.foregroundColor
                            // highlightColor: mainWindow.highlightColor
                            // accentColor: mainWindow.accentColor
                        }

                        // Auto-scroll logic
                        onContentHeightChanged: positionViewAtBeginning()
                        Component.onCompleted: positionViewAtBeginning()
                    }
                } // End Messages ScrollView

                // Thinking/Loading Indicator
                Rectangle {
                    id: thinkingIndicator
                    Layout.fillWidth: true
                    height: visible ? 30 : 0
                    color: highlightColor
                    radius: 4
                    visible: isLoading // Bound to global loading state
                    Behavior on height {
                        NumberAnimation {
                            duration: 150
                        }
                    }

                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 8
                        visible: parent.visible

                        BusyIndicator {
                            width: 20; height: 20; running: thinkingIndicator.visible
                        }
                        Label {
                            text: "Thinking..."; color: foregroundColor; Layout.fillWidth: true; verticalAlignment: Text.AlignVCenter
                        }
                    }
                } // End Thinking Indicator

                // File Attachments Staging Area
                Rectangle {
                    id: attachmentsArea
                    Layout.fillWidth: true
                    height: visible ? 60 : 0
                    color: highlightColor
                    radius: 4
                    visible: fileAttachmentsModel.count > 0
                    Behavior on height {
                        NumberAnimation {
                            duration: 150
                        }
                    }

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 4
                        visible: parent.visible

                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: "Attachments: " + fileAttachmentsModel.count; color: foregroundColor; Layout.fillWidth: true; verticalAlignment: Text.AlignVCenter
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

                        ListView {
                            id: attachmentsView
                            Layout.fillWidth: true; Layout.fillHeight: true
                            orientation: ListView.Horizontal
                            spacing: 8
                            model: fileAttachmentsModel

                            delegate: Rectangle {
                                width: 150; height: attachmentsView.height
                                color: accentColor; radius: 4

                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 4; spacing: 4

                                    Label {
                                        text: model.fileName; color: foregroundColor; elide: Text.ElideRight
                                        Layout.fillWidth: true; verticalAlignment: Text.AlignVCenter
                                        ToolTip.text: model.fileName + "\n" + (model.fileSize || "Pending..."); ToolTip.visible: hovered
                                    }
                                    Button {
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
                            } // End delegate
                        } // End Attachments ListView
                    } // End Attachments ColumnLayout
                } // End Attachments Area

                // Input Area
                Rectangle {
                    id: inputArea
                    Layout.fillWidth: true
                    height: Math.min(Math.max(inputField.implicitHeight + 20, 80), 200)
                    color: highlightColor
                    radius: 4

                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 8

                        TextArea {
                            id: inputField
                            Layout.fillWidth: true; Layout.fillHeight: true
                            placeholderText: "Type your message (Shift+Enter for newline)..."
                            color: foregroundColor
                            background: Rectangle {
                                color: "transparent"
                            }
                            wrapMode: TextEdit.Wrap; font.pixelSize: 14
                            enabled: !isLoading // Disable input during global loading

                            Keys.onPressed: (event) => {
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    if (event.modifiers & Qt.ShiftModifier) {
                                        event.accepted = false; // Insert newline
                                    } else {
                                        sendMessage(); // Send message
                                        event.accepted = true; // Consume event
                                    }
                                } else {
                                    event.accepted = false; // Allow other keys
                                }
                            }
                        } // End Input TextArea

                        // Action Buttons Column
                        ColumnLayout {
                            Layout.preferredWidth: 40; spacing: 8

                            Button { // Send Button
                                id: sendButton
                                text: "➤"; ToolTip.text: "Send Message (Enter)"; ToolTip.visible: hovered
                                Layout.fillWidth: true; Layout.preferredHeight: 40
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
                                text: "↺"; ToolTip.text: "Retry Last Response"; ToolTip.visible: hovered
                                Layout.fillWidth: true; Layout.preferredHeight: 40
                                enabled: !isLoading && messagesModel.count > 0 && currentBranch.length > 0 && currentBranch[currentBranch.length - 1].role === 'assistant'
                                onClicked: { if (conversationViewModel) conversationViewModel.retry_last_response(); }
                                background: Rectangle {
                                    color: retryButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5); radius: 4; border.color: accentColor; border.width: 1
                                }
                                contentItem: Text {
                                    text: "↺"; color: foregroundColor; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                            Button { // Attach Button
                                id: attachButton
                                text: "📎"; ToolTip.text: "Attach File"; ToolTip.visible: hovered
                                Layout.fillWidth: true; Layout.preferredHeight: 40
                                enabled: !isLoading
                                onClicked: fileDialog.open()
                                background: Rectangle {
                                    color: attachButton.enabled ? highlightColor : Qt.rgba(0.27, 0.28, 0.35, 0.5); radius: 4; border.color: accentColor; border.width: 1
                                }
                                contentItem: Text {
                                    text: "📎"; color: foregroundColor; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                }
                            }
                        } // End Action Buttons Column
                    } // End Input RowLayout
                } // End Input Area Rectangle

                // Status Bar (Tokens, Model)
                Rectangle {
                    id: statusBar
                    Layout.fillWidth: true; height: 30
                    color: highlightColor; radius: 4

                    RowLayout {
                        anchors.fill: parent; anchors.margins: 8; spacing: 8

                        Label {
                            id: tokenUsageText
                            text: "Tokens: N/A" // Updated by signal
                            color: foregroundColor; opacity: 0.8
                            Layout.fillWidth: true
                            verticalAlignment: Text.AlignVCenter
                        }
                        Label {
                            id: modelInfoText
                            // Bind directly to ViewModel property if available, otherwise use signal connection
                            text: "Model: " + (settingsViewModel ? (settingsViewModel.get_setting("model") || "N/A") : "N/A")
                            color: foregroundColor; opacity: 0.8
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                } // End Status Bar
            } // End Main Chat Area ColumnLayout
        } // End Main Chat Area Rectangle
    } // End SplitView

    // --- Dialogs ---
    FileDialog {
        id: fileDialog
        title: "Attach File(s)"
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            for (var i = 0; i < selectedFiles.length; i++) {
                handleFileSelected(selectedFiles[i]);
            }
        }
    }

    Dialog {
        id: saveDialog
        title: "Save Conversations"; standardButtons: Dialog.Ok; modal: true; width: 350
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        contentItem: Label {
            text: "Conversations are saved automatically."; color: foregroundColor; padding: 16; wrapMode: Text.WordWrap
        }
    }

    Dialog {
        id: errorDialog
        title: "Error"; standardButtons: Dialog.Ok; modal: true; width: 400
        property string text: ""
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: errorColor; border.width: 1
        }
        contentItem: Label {
            text: errorDialog.text; color: foregroundColor; padding: 16; wrapMode: Text.WordWrap
        }
    }

    Dialog {
        id: renameDialog
        title: "Rename Conversation"; standardButtons: Dialog.Ok | Dialog.Cancel; modal: true; width: 400
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        onAccepted: {
            if (conversationList.currentIndex >= 0 && conversationViewModel) {
                const conversationId = conversationsModel.get(conversationList.currentIndex).id;
                conversationViewModel.rename_conversation(conversationId, renameField.text);
            }
        }
        contentItem: ColumnLayout {
            id: contentColumn; width: renameDialog.width - 32; spacing: 16
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
        Component.onCompleted: height = contentColumn.implicitHeight + 80
        onOpened: { if (conversationList.currentIndex >= 0) renameField.text = conversationsModel.get(conversationList.currentIndex).name; }
    }

    Dialog {
        id: aboutDialog
        title: "About CannonAI"; standardButtons: Dialog.Close; modal: true; width: 400
        background: Rectangle {
            color: backgroundColor; radius: 8; border.color: accentColor; border.width: 1
        }
        contentItem: ColumnLayout {
            width: parent.width - 32; spacing: 16
            Label {
                text: "CannonAI Chat Interface"; color: foregroundColor; font.bold: true; font.pixelSize: 16
            }
            Label {
                text: "A desktop application using PyQt6 and MVVM for interacting with AI models.\n\nVersion: 1.0.0 (Placeholder)"; color: foregroundColor; wrapMode: Text.WordWrap
            }
        }
        Component.onCompleted: height = contentItem.implicitHeight + 80
    }

    Dialog {
        id: deleteConfirmDialog
        title: "Delete Conversation"; standardButtons: Dialog.Yes | Dialog.No; modal: true; width: 400
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
        objectName: "settingsDialog"

        // Ensure connection is active
        onSettingsSaved: (settings) => {
            if (settingsViewModel) {
                console.log("MainWindow: Forwarding settingsSaved signal to settingsViewModel.");
                settingsViewModel.update_settings(settings);
            } else {
                console.error("MainWindow: Cannot save settings, settingsViewModel is null.");
                errorDialog.text = "Settings functionality is unavailable.";
                errorDialog.open();
            }
        }
        // Pass theme colors if needed
        // backgroundColor: mainWindow.backgroundColor // etc.
    }

    // Search Dialog
    Components.SearchDialog {
        id: searchDialog
        objectName: "searchDialog"

        // Connect SearchDialog signals to ConversationViewModel slots
        onSearchRequested: (term, searchAll, convId) => {
            if (conversationViewModel) {
                console.log("MainWindow: Forwarding search request to ViewModel.");
                conversationViewModel.start_search(term, searchAll, convId);
            } else {
                console.error("MainWindow: Cannot start search, conversationViewModel is null.");
                errorDialog.text = "Search functionality is unavailable.";
                errorDialog.open();
                searchDialog.isSearching = false; // Ensure indicator stops
            }
        }
        onResultSelected: (convId, msgId) => {
            if (conversationViewModel) {
                console.log("MainWindow: Forwarding result selection to ViewModel (convId: " + convId + ", msgId: " + msgId + ")");
                // Load conversation if necessary, then navigate. ViewModel should handle the sequence.
                // Simple approach: Load first, navigate relies on load completing.
                if (!currentConversation || currentConversation.id !== convId) {
                    console.log("MainWindow: Loading conversation " + convId + " before navigating.");
                    conversationViewModel.load_conversation(convId);
                    // Assume load_conversation will trigger branch load for the target message eventually
                    // Or potentially navigate_to_message needs to be smarter or called after load signal
                }
                // Always call navigate - if conv is loaded, it updates node; if not, load call above should handle it.
                // This relies on VM handling the sequence correctly.
                conversationViewModel.navigate_to_message(msgId);

            } else {
                console.error("MainWindow: Cannot navigate to result, conversationViewModel is null.");
            }
        }
        // Pass theme colors if needed
        // backgroundColor: mainWindow.backgroundColor // etc.
    }

    // --- Utility Functions ---
    function handleFileSelected(fileUrl) {
        // Use PythonBridge singleton if available, otherwise basic parsing
        let filePath = "";
        try {
            // Assuming PythonBridge is registered globally as PythonBridge
            if (typeof PythonBridge !== "undefined" && PythonBridge.bridge) {
                filePath = PythonBridge.fileUrlToPath(fileUrl);
            } else {
                // Basic fallback parsing (might not cover all edge cases)
                let pathStr = fileUrl.toString();
                if (pathStr.startsWith("file:///")) {
                    pathStr = pathStr.substring(Qt.platform.os === "windows" ? 8 : 7);
                } else if (pathStr.startsWith("file://")) {
                    pathStr = pathStr.substring(7);
                }
                filePath = decodeURIComponent(pathStr);
            }
        } catch (e) {
            console.error("QML: Error converting file URL to path:", e);
            errorDialog.text = "Could not process selected file path.";
            errorDialog.open();
            return;
        }

        if (!filePath) {
            console.error("QML: Could not determine file path from URL:", fileUrl);
            return;
        }

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

    function sendMessage() {
        if (!conversationViewModel || !currentConversation) {
            console.error("Cannot send message: ViewModel or conversation not ready.");
            errorDialog.text = "Please select or create a conversation first.";
            errorDialog.open();
            return;
        }
        if (inputField.text.trim() === "") return;

        let attachmentsData = [];
        for (let i = 0; i < fileAttachmentsModel.count; i++) {
            const item = fileAttachmentsModel.get(i);
            attachmentsData.push({
                fileName: item.fileName,
                filePath: item.filePath
            });
        }

        console.log("QML: Sending message in conversation:", currentConversation.id);
        // Convert attachmentsData to QVariant if sending complex objects
        conversationViewModel.send_message(currentConversation.id, inputField.text, attachmentsData);

        inputField.text = ""; // Clear input field
        fileAttachmentsModel.clear(); // Clear staged attachments
    }

    function duplicateConversation() {
        if (!conversationViewModel || !currentConversation) {
            console.error("Cannot duplicate: ViewModel or current conversation not available.");
            return;
        }
        console.log("QML: Requesting duplication of conversation:", currentConversation.id);
        // Call the ViewModel slot
        conversationViewModel.duplicate_conversation(currentConversation.id, currentConversation.name + " (Copy)");
    }

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

    function updateBranchNavigation(branch) {
        branchNavRow.children = [];
        if (!branch || branch.length <= 1) {
            branchNavBar.visible = false;
            return;
        }
        branchNavBar.visible = true;

        let visibleItemCount = 0;
        for (let i = 0; i < branch.length; i++) {
            const node = branch[i];
            if (node.role === "system" && i > 0) continue; // Skip mid-conversation system messages

            visibleItemCount++;
            let buttonText = "";
            if (node.role === "user") buttonText = "👤 User";
            else if (node.role === "assistant") buttonText = "🤖 Asst";
            else buttonText = "🔧 Sys";

            // Create navigation button dynamically
            const button = Qt.createQmlObject(
                'import QtQuick.Controls 2.15; import QtQuick 2.15; Button { \
                    text: qsTr("' + buttonText + '"); \
                    property string nodeId: "' + node.id + '"; \
                    flat: true; \
                    enabled: !mainWindow.isLoading; \
                    background: Rectangle { color: "transparent" } \
                    contentItem: Text { \
                        text: parent.text; \
                        color: ' + (i === branch.length - 1 ? 'mainWindow.accentColor' : 'mainWindow.foregroundColor') + '; \
                        font.bold: ' + (i === branch.length - 1) + '; \
                        opacity: ' + (i === branch.length - 1 ? 1.0 : 0.7) + '; \
                    } \
                    onClicked: { \
                        if (mainWindow.conversationViewModel && nodeId !== mainWindow.currentBranch[mainWindow.currentBranch.length-1].id && !mainWindow.isLoading) { \
                            console.log("QML: Navigating to message:", nodeId); \
                            mainWindow.conversationViewModel.navigate_to_message(nodeId); \
                        } \
                    } \
                    ToolTip.text: "Go to this message"; ToolTip.visible: hovered; ToolTip.delay: 500; \
                }',
                branchNavRow,
                "navButton_" + node.id // Use message ID for potentially more stable object name
            );

            // Add arrow separator if not the last *visible* item
            let nextVisibleIndex = -1;
            for (let j = i + 1; j < branch.length; j++) {
                if (!(branch[j].role === "system" && j > 0)) { // Same visibility condition
                    nextVisibleIndex = j;
                    break;
                }
            }
            if (nextVisibleIndex !== -1) {
                Qt.createQmlObject(
                    'import QtQuick 2.15; Text { text: "→"; color: mainWindow.foregroundColor; opacity: 0.5; anchors.verticalCenter: parent.verticalCenter }',
                    branchNavRow, "arrow_" + node.id
                );
            }
        }
    }

    // Function to scroll message view (no changes needed)
    function positionViewAtBeginning() {
        // For BottomToTop, positionViewAtBeginning shows the newest items
        if (messagesView.contentHeight > messagesScroll.height) {
            messagesView.positionViewAtBeginning();
        }
    }

    // --- ViewModel Signal Connections ---
    Connections {
        target: conversationViewModel
        enabled: conversationViewModel !== null

        function onConversationListUpdated(convList) {
            console.log("QML: Received conversationListUpdated signal with", convList ? convList.length : 0, "items.");
            conversationsModel.clear();
            if (!convList) return;
            for (let i = 0; i < convList.length; i++) conversationsModel.append(convList[i]);

            // Select first item if nothing is selected, VM handles loading it
            if (convList.length > 0 && conversationList.currentIndex === -1) {
                console.log("QML: Auto-selecting first conversation in list:", convList[0].id);
                conversationList.currentIndex = 0;
                // ViewModel's _handle_conversation_list_loaded triggers loading the first one
            } else if (convList.length === 0) {
                // Clear chat if no conversations left
                messagesModel.clear();
                currentConversation = null;
                currentBranch = [];
                updateBranchNavigation([]);
            } else {
                // Ensure selection is still valid if list updated
                if (conversationList.currentIndex >= convList.length) {
                    conversationList.currentIndex = convList.length - 1;
                    // VM should load this one if selection changed
                    if (conversationList.currentIndex >= 0) {
                        conversationViewModel.load_conversation(conversationsModel.get(conversationList.currentIndex).id);
                    }
                } else if (currentConversation && conversationList.currentIndex >= 0) {
                    // Refresh data for the currently selected item in case name changed
                    const selectedModelData = conversationsModel.get(conversationList.currentIndex);
                    if (selectedModelData && selectedModelData.id === currentConversation.id) {
                        conversationsModel.setProperty(conversationList.currentIndex, "name", currentConversation.name);
                        conversationsModel.setProperty(conversationList.currentIndex, "modified_at", currentConversation.modified_at);
                    }
                }
            }
        }

        function onConversationLoaded(conversation) {
            console.log("QML: Received conversationLoaded signal for:", conversation ? conversation.id : "null");
            if (!conversation) {
                // Handle case where load failed or returned null
                currentConversation = null;
                messagesModel.clear();
                currentBranch = [];
                updateBranchNavigation([]);
                return;
            }
            currentConversation = conversation; // Update current conversation state

            // Ensure list selection matches loaded conversation
            let found = false;
            for (let i = 0; i < conversationsModel.count; i++) {
                if (conversationsModel.get(i).id === conversation.id) {
                    if (conversationList.currentIndex !== i) {
                        console.log("QML: Updating conversationList currentIndex to match loaded conversation.");
                        conversationList.currentIndex = i;
                    }
                    // Update list item data if necessary (name might have changed)
                    conversationsModel.setProperty(i, "name", conversation.name);
                    conversationsModel.setProperty(i, "modified_at", conversation.modified_at);
                    found = true;
                    break;
                }
            }
            if (!found) console.warn("QML: Loaded conversation ID not found in conversationsModel!");
            // ViewModel should handle triggering branch loading via its own logic after load completes
            // (Handled in _handle_conversation_loaded in VM)
        }

        function onMessageBranchChanged(branch) {
            console.log("QML: Received messageBranchChanged signal with", branch.length, "messages.");
            currentBranch = branch || []; // Update state, ensure it's an array
            messagesModel.clear();
            let isStreamingPlaceholder = false;
            for (let i = 0; i < currentBranch.length; i++) {
                const node = currentBranch[i];
                // Basic check for node structure
                if (!node || typeof node.id === 'undefined' || typeof node.role === 'undefined') {
                    console.error("QML: Invalid message node received in branch:", node);
                    continue; // Skip invalid node
                }
                messagesModel.append({
                    id: node.id, role: node.role, content: node.content || "",
                    timestamp: node.timestamp || new Date().toISOString(),
                    attachments: node.file_attachments || [] // Ensure attachments is always an array
                });
                // Check if last message is a temporary streaming one
                if (i === currentBranch.length - 1 && node.role === 'assistant' && node.id && node.id.toString().startsWith('temp-')) {
                    isStreamingPlaceholder = true;
                }
            }
            updateBranchNavigation(currentBranch);
            // Use timer to ensure layout is updated before scrolling
            Qt.callLater(positionViewAtBeginning);
        }

        function onMessageStreamChunk(chunk) {
            // console.log("QML: Stream chunk:", chunk); // Can be very noisy
            if (messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1;
                let lastMessage = messagesModel.get(lastIndex);
                // Append to last assistant message OR add new temporary assistant message
                if (lastMessage.role === "assistant") {
                    messagesModel.setProperty(lastIndex, "content", lastMessage.content + chunk);
                } else {
                    // Last message was user, add new temp assistant message
                    messagesModel.append({id: "temp-" + Date.now(), role: "assistant", content: chunk, timestamp: new Date().toISOString(), attachments: []});
                }
                Qt.callLater(positionViewAtBeginning); // Scroll during stream
            } else { // First message in conversation is streaming
                messagesModel.append({id: "temp-" + Date.now(), role: "assistant", content: chunk, timestamp: new Date().toISOString(), attachments: []});
                Qt.callLater(positionViewAtBeginning);
            }
        }

        function onMessageAdded(message) {
            // This signal is emitted when a *final* message (user or assistant) is saved
            // It's often followed by onMessageBranchChanged, but can update UI slightly faster
            console.log("QML: Received messageAdded signal for:", message.id, "Role:", message.role);

            if (message.role === 'assistant' && messagesModel.count > 0) {
                const lastIndex = messagesModel.count - 1;
                let lastMessage = messagesModel.get(lastIndex);
                // If the last message in the model was the temporary streaming one, replace it
                if (lastMessage.id && lastMessage.id.toString().startsWith("temp-")) {
                    console.log("QML: Replacing temporary streaming message with final:", message.id);
                    // Update properties of the existing item
                    messagesModel.setProperty(lastIndex, "id", message.id);
                    messagesModel.setProperty(lastIndex, "content", message.content || "");
                    messagesModel.setProperty(lastIndex, "timestamp", message.timestamp || new Date().toISOString());
                    messagesModel.setProperty(lastIndex, "attachments", message.file_attachments || []);
                } else if (lastMessage.id !== message.id) {
                    // This might happen if branch change signal arrives slightly later.
                    // Avoid appending duplicates if the branch change will handle it.
                    console.warn("QML: messageAdded received, but last message wasn't temporary or ID differs. Branch change should handle addition.");
                    // messagesModel.append({...}); // Avoid appending here usually
                }
            } else if (message.role === 'user') {
                // Append the user message if it's not already the last item
                if (messagesModel.count === 0 || messagesModel.get(messagesModel.count - 1).id !== message.id) {
                    console.log("QML: Appending user message from messageAdded signal.");
                    messagesModel.append({
                        id: message.id, role: message.role, content: message.content || "",
                        timestamp: message.timestamp || new Date().toISOString(),
                        attachments: message.file_attachments || []
                    });
                }
            }
            Qt.callLater(positionViewAtBeginning);
        }

        function onTokenUsageUpdated(usage) {
            let tokenText = "Tokens: ";
            tokenText += (usage && usage.completion_tokens !== undefined && usage.total_tokens !== undefined)
                ? `${usage.completion_tokens} / ${usage.total_tokens}` : "N/A";
            tokenUsageText.text = tokenText;
        }

        function onLoadingStateChanged(loading) {
            console.log("QML: Received loadingStateChanged signal:", loading);
            isLoading = loading; // Update global loading state
        }

        // Handle search results from ViewModel
        function onSearchResultsReady(results) {
            console.log("MainWindow: Received searchResultsReady signal with " + (results ? results.length : 0) + " items.");
            if (searchDialog) {
                searchDialog.searchResults = results; // Update the dialog's property
                // The dialog's onSearchResultsChanged handler will update its internal model
                // and set isSearching = false.
            }
        }

        function onErrorOccurred(errorMessage) {
            console.error("QML: Received errorOccurred signal from ViewModel:", errorMessage);
            errorDialog.title = "Application Error";
            errorDialog.text = errorMessage;
            errorDialog.open();

            // If an error occurs, assume any ongoing search should stop visually
            if (searchDialog && searchDialog.isSearching) {
                console.log("MainWindow: Stopping search indicator due to error.");
                searchDialog.isSearching = false;
            }
            // Also ensure global loading indicator stops on error
            if (isLoading) {
                isLoading = false;
            }
        }

        function onReasoningStepsChanged(steps) {
            console.log("QML: Received reasoningStepsChanged signal with", steps ? steps.length : 0, "steps.");
            // TODO: Display reasoning steps
        }

        function onMessagingComplete() {
            console.log("QML: Received messagingComplete signal.");
            // Ensure input is enabled if it wasn't already (isLoading should be false by now)
            // inputField.enabled = !isLoading;
        }
    } // End Connections for conversationViewModel

    Connections {
        target: settingsViewModel
        enabled: settingsViewModel !== null

        function onSettingChanged(key, value) {
            if (key === "model") {
                modelInfoText.text = "Model: " + (value || "N/A");
            }
            // Update other UI elements if needed based on single setting changes
        }

        function onSettingsChanged(settings) {
            // Update UI based on the full settings object
            if (settings && settings.model) {
                modelInfoText.text = "Model: " + settings.model;
            }
            // Potentially update theme, etc.
        }
    } // End Connections for settingsViewModel

} // End ApplicationWindow