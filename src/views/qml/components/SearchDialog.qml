// src/views/qml/components/SearchDialog.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: searchDialog
    title: "Search Conversations"
    width: 500
    height: 400
    modal: true

    // Properties
    property string currentConversationId: ""
    property bool searchAllConversations: true

    // Search results model
    ListModel {
        id: searchResultsModel
    }

    // Custom background and styling
    background: Rectangle {
        color: backgroundColor
        radius: 8
        border.color: accentColor
        border.width: 1
    }

    // Main content
    contentItem: ColumnLayout {
        spacing: 16

        Rectangle {
                id: searchingIndicator
                width: resultsList.width
                height: 30
                color: highlightColor
                visible: false

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    BusyIndicator {
                        width: 20
                        height: 20
                        running: searchingIndicator.visible
                    }

                    Text {
                        text: "Searching..."
                        color: foregroundColor
                        Layout.fillWidth: true
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

                onAccepted: performSearch()
            }

            Button {
                text: "Search"
                implicitWidth: 80
                onClicked: performSearch()

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

        // Search scope option
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: "Search scope:"
                color: foregroundColor
            }

            RadioButton {
                id: currentConvRadio
                text: "Current conversation"
                checked: !searchAllConversations
                onCheckedChanged: searchAllConversations = !checked

                contentItem: Text {
                    text: currentConvRadio.text
                    color: foregroundColor
                    leftPadding: currentConvRadio.indicator.width + currentConvRadio.spacing
                    verticalAlignment: Text.AlignVCenter
                }
            }

            RadioButton {
                id: allConvsRadio
                text: "All conversations"
                checked: searchAllConversations
                onCheckedChanged: searchAllConversations = checked

                contentItem: Text {
                    text: allConvsRadio.text
                    color: foregroundColor
                    leftPadding: allConvsRadio.indicator.width + allConvsRadio.spacing
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // Search results
        Text {
            text: "Results:"
            color: foregroundColor
            font.bold: true
            visible: searchResultsModel.count > 0
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            visible: searchResultsModel.count > 0

            ListView {
                id: resultsList
                anchors.fill: parent
                model: searchResultsModel
                spacing: 4

                delegate: Rectangle {
                    width: resultsList.width
                    height: resultLayout.implicitHeight + 16
                    color: highlightColor
                    radius: 4

                    MouseArea {
                        anchors.fill: parent
                        onClicked: navigateToResult(model.conversation_id, model.id)
                    }

                    ColumnLayout {
                        id: resultLayout
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Text {
                                text: {
                                    if (model.role === "user") return "👤 User"
                                    else if (model.role === "assistant") return "🤖 Assistant"
                                    else return "🔧 System"
                                }
                                color: {
                                    if (model.role === "user") return userMessageColor
                                    else if (model.role === "assistant") return assistantMessageColor
                                    else return systemMessageColor
                                }
                                font.bold: true
                            }

                            Text {
                                text: model.conversation_name
                                color: foregroundColor
                                font.italic: true
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignRight
                            }
                        }

                        Text {
                            text: model.content.length > 200 ? model.content.substring(0, 200) + "..." : model.content
                            color: foregroundColor
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        // No results message
        Text {
            text: "No results found. Try a different search term."
            color: foregroundColor
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            visible: searchField.text !== "" && searchResultsModel.count === 0
        }
    }

    // Footer buttons
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

    // Search function
    function performSearch() {
        const searchTerm = searchField.text.trim()
        if (searchTerm === "") return

        // Clear previous results
        searchResultsModel.clear()

        // Call ViewModel search method
        const results = conversationViewModel.search_conversations(
            searchTerm,
            searchAllConversations ? null : currentConversationId
        )

        // Populate results model
        for (let i = 0; i < results.length; i++) {
            searchResultsModel.append(results[i])
        }
    }

    // Navigate to a search result
    function navigateToResult(conversationId, messageId) {
        // First load the conversation if needed
        if (conversationId !== currentConversationId) {
            conversationViewModel.load_conversation(conversationId)
        }

        // Then navigate to the specific message
        conversationViewModel.navigate_to_message(messageId)

        // Close the dialog
        searchDialog.close()
    }

    // Initialize dialog
    function initialize(convId) {
        currentConversationId = convId
        searchField.text = ""
        searchResultsModel.clear()
    }
}