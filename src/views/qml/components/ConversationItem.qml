// src/views/qml/components/ConversationItem.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: conversationItem
    width: ListView.view ? ListView.view.width : 250
    height: 60
    color: ListView.isCurrentItem ? accentColor : "transparent"
    radius: 4

    // Properties from parent ListView's model
    property string conversationId: model.id || ""
    property string conversationName: model.name || "New Conversation"
    property string conversationDate: model.modified_at || ""
    property bool isActive: ListView.isCurrentItem

    // Custom signals
    signal itemClicked()
    signal itemRightClicked()
    signal itemDoubleClicked()

    // Mouse interaction area
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton

        onClicked: function(mouse) {
            if (mouse.button === Qt.LeftButton) {
                conversationItem.itemClicked()
            } else if (mouse.button === Qt.RightButton) {
                conversationItem.itemRightClicked()
            }
        }

        onDoubleClicked: conversationItem.itemDoubleClicked()

        // Hover effect
        hoverEnabled: true
        onEntered: {
            if (!conversationItem.isActive) {
                conversationItem.color = Qt.rgba(0.27, 0.28, 0.35, 0.5) // Lighter highlight
            }
        }
        onExited: {
            if (!conversationItem.isActive) {
                conversationItem.color = "transparent"
            }
        }
    }

    // Content layout
    RowLayout {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 8

        // Icon or avatar
        Rectangle {
            width: 36
            height: 36
            radius: 18
            color: accentColor

            Text {
                anchors.centerIn: parent
                text: "💬"
                font.pixelSize: 18
            }
        }

        // Text content
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                text: conversationName
                color: foregroundColor
                font.bold: conversationItem.isActive
                font.pixelSize: 14
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                text: formatDate(conversationDate)
                color: foregroundColor
                opacity: 0.7
                font.pixelSize: 11
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
    }

    // Helper function for date formatting
    function formatDate(dateString) {
        if (!dateString) return "New"

        const date = new Date(dateString)
        const now = new Date()
        const diffMs = now - date
        const diffMins = Math.floor(diffMs / 60000)
        const diffHours = Math.floor(diffMins / 60)
        const diffDays = Math.floor(diffHours / 24)

        if (diffMins < 60) {
            return diffMins + " min ago"
        } else if (diffHours < 24) {
            return diffHours + " hr ago"
        } else if (diffDays < 7) {
            return diffDays + " day" + (diffDays > 1 ? "s" : "") + " ago"
        } else {
            return date.toLocaleDateString()
        }
    }
}