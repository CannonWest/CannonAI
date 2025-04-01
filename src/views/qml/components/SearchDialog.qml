// src/views/qml/components/SearchDialog.qml
// Version: Updated for MVVM signal emission

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: searchDialog
    objectName: "searchDialog" // Added objectName for easier access if needed
    title: "Search Conversations"
    width: 500
    height: 400
    modal: true

    // Properties
    property string currentConversationId: ""
    property bool searchAllConversations: true
    property bool isSearching: false // Added property for busy indicator

    // Search results - This will be SET externally by the ViewModel via MainWindow
    property var searchResults: []

    // Signals emitted to be handled by the ViewModel via MainWindow
    signal searchRequested(string searchTerm, bool searchAll, string conversationId)
    signal resultSelected(string conversationId, string messageId)

    // Internal Search results model - NOW POPULATED BY 'searchResults' PROPERTY CHANGE
    ListModel {
        id: searchResultsModel
    }

    // Update internal model when external property changes
    onSearchResultsChanged: {
        console.log("SearchDialog: searchResults property updated, refreshing model.");
        searchResultsModel.clear();
        if (searchResults) {
            for (var i = 0; i < searchResults.length; i++) {
                searchResultsModel.append(searchResults[i]);
            }
        }
        isSearching = false; // Turn off indicator when results arrive (or error occurs)
    }


    // Custom background and styling (Keep as is)
    background: Rectangle {
        color: backgroundColor // Assuming these are passed or globally available
        radius: 8
        border.color: accentColor
        border.width: 1
    }

    // Main content
    contentItem: ColumnLayout {
        spacing: 16

        // --- Busy Indicator ---
        Rectangle {
            id: searchingIndicator
            Layout.fillWidth: true
            // Animate height change for smooth appearance/disappearance
            height: searchDialog.isSearching ? 30 : 0
            color: highlightColor
            visible: height > 0 // Only visible when height > 0
            Behavior on height { NumberAnimation { duration: 150 } }

            RowLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                visible: parent.visible // Hide content when collapsed

                BusyIndicator {
                    width: 20; height: 20
                    running: searchDialog.isSearching
                }
                Label { // Use Label
                    text: "Searching..."
                    color: foregroundColor
                    Layout.fillWidth: true
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }


        // Search options
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Enter search term..."
                color: foregroundColor

                background: Rectangle {
                    color: highlightColor
                    radius: 4
                }

                onAccepted: performSearch() // Trigger search on Enter
                // Clear previous results visually when typing starts? Optional.
                // onTextChanged: if (searchResultsModel.count > 0) searchResultsModel.clear()
            }

            Button {
                text: "Search"
                implicitWidth: 80
                onClicked: performSearch() // Trigger search on click
                enabled: !searchDialog.isSearching // Disable during search

                background: Rectangle {
                    color: accentColor
                    radius: 4
                }

                contentItem: Text {
                    text: "Search"
                    color: foregroundColor
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // Search scope option (Keep as is)
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Label { // Use Label
                text: "Search scope:"
                color: foregroundColor
            }

            RadioButton {
                id: currentConvRadio
                text: "Current conversation"
                checked: !searchAllConversations
                onCheckedChanged: searchAllConversations = !checked
                enabled: currentConversationId !== "" // Only enable if a conversation is active

                indicator: Rectangle {
                     implicitWidth: 16; implicitHeight: 16; radius: 8
                     border.color: parent.checked ? accentColor : foregroundColor
                     border.width: 1
                     Rectangle { anchors.fill: parent; anchors.margins: 4; radius: 4; color: parent.checked ? accentColor : "transparent" }
                 }
                contentItem: Label { // Use Label
                    text: parent.text
                    color: foregroundColor
                    leftPadding: parent.indicator.width + parent.spacing
                    verticalAlignment: Text.AlignVCenter
                }
            }

            RadioButton {
                id: allConvsRadio
                text: "All conversations"
                checked: searchAllConversations
                onCheckedChanged: searchAllConversations = checked

                 indicator: Rectangle {
                     implicitWidth: 16; implicitHeight: 16; radius: 8
                     border.color: parent.checked ? accentColor : foregroundColor
                     border.width: 1
                     Rectangle { anchors.fill: parent; anchors.margins: 4; radius: 4; color: parent.checked ? accentColor : "transparent" }
                 }
                contentItem: Label { // Use Label
                    text: parent.text
                    color: foregroundColor
                    leftPadding: parent.indicator.width + parent.spacing
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // Search results heading (Keep as is)
        Label { // Use Label
            text: "Results:"
            color: foregroundColor
            font.bold: true
            visible: searchResultsModel.count > 0
        }

        // Search results list view
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            // visible: searchResultsModel.count > 0 // Keep visible to show 'No results' message below if needed

            ListView {
                id: resultsList
                anchors.fill: parent
                model: searchResultsModel // Uses internal model populated by property change
                spacing: 4

                delegate: Rectangle {
                    width: resultsList.width
                    // Use implicit height based on content + padding
                    implicitHeight: resultLayout.implicitHeight + 16
                    color: highlightColor // Use theme color
                    radius: 4

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        // Call the MODIFIED navigateToResult function
                        onClicked: navigateToResult(model.conversation_id, model.id)

                        // Hover effect
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: parent.containsMouse ? Qt.lighter(highlightColor, 1.2) : "transparent"
                            border.color: parent.containsMouse ? accentColor : "transparent"
                            border.width: 1
                            z: -1 // Place behind content
                        }
                    }

                    ColumnLayout {
                        id: resultLayout
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label { // Use Label
                                text: {
                                    if (model.role === "user") return "👤 User"
                                    else if (model.role === "assistant") return "🤖 Assistant"
                                    else return "🔧 System"
                                }
                                color: { // Use theme colors
                                    if (model.role === "user") return userMessageColor
                                    else if (model.role === "assistant") return assistantMessageColor
                                    else return systemMessageColor
                                }
                                font.bold: true
                            }

                            Label { // Use Label
                                text: model.conversation_name // Assuming this is passed in results
                                color: foregroundColor
                                font.italic: true
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        Label { // Use Label for message content
                            // Use RichText for potential highlighting later? For now, PlainText.
                            // textFormat: Text.RichText
                            text: model.content.length > 200 ? model.content.substring(0, 200) + "..." : model.content
                            color: foregroundColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                } // End delegate
            } // End ListView
        } // End ScrollView

        // No results message
        Label { // Use Label
            text: "No results found."
            color: foregroundColor
            opacity: 0.7
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            // Show when search performed, not searching, and no results
            visible: !searchDialog.isSearching && searchField.text.trim() !== "" && searchResultsModel.count === 0
        }
    } // End contentItem ColumnLayout

    // Footer buttons (Keep as is)
    footer: DialogButtonBox {
        Button {
            text: "Close"
            DialogButtonBox.buttonRole: DialogButtonBox.RejectRole

            background: Rectangle {
                color: highlightColor
                radius: 4
            }

            contentItem: Text {
                text: "Close"
                color: foregroundColor
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    // --- MODIFIED QML Functions ---

    // Function to trigger search signal
    function performSearch() {
        const searchTerm = searchField.text.trim()
        if (searchTerm === "" || searchDialog.isSearching) return // Prevent empty or concurrent searches

        console.log("SearchDialog: Emitting searchRequested signal.");
        isSearching = true; // Set busy indicator
        searchResultsModel.clear(); // Clear previous results visually

        // Emit signal with search term, scope, and current conversation ID
        searchDialog.searchRequested(
            searchTerm,
            searchAllConversations,
            searchAllConversations ? "" : currentConversationId // Pass empty string if searching all
        );
    }

    // Function to trigger result selection signal
    function navigateToResult(conversationId, messageId) {
        console.log("SearchDialog: Emitting resultSelected signal.");
        // Emit signal with IDs for ViewModel to handle navigation
        searchDialog.resultSelected(conversationId, messageId);

        // Close the dialog after selection
        searchDialog.close();
    }

    // Initialize dialog (Keep mostly as is, but clear results property)
    function initialize(convId) {
        console.log("SearchDialog: Initializing.");
        currentConversationId = convId || "";
        searchField.text = "";
        searchResults = []; // Clear the results property
        searchResultsModel.clear(); // Clear internal model
        isSearching = false;
        // Default to searching all if no specific convId is provided
        searchAllConversations = (currentConversationId === "");
        allConvsRadio.checked = searchAllConversations;
        currentConvRadio.checked = !searchAllConversations;
        currentConvRadio.enabled = (currentConversationId !== ""); // Enable/disable radio button
    }

    // Ensure busy indicator stops if dialog is rejected while searching
    onRejected: {
        isSearching = false;
    }

} // End Dialog