// src/views/qml/components/MessageDelegate.qml

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: messageContainer
    width: parent ? parent.width : 0
    implicitHeight: contentColumn.implicitHeight + 24
    color: {
        // Set background color based on role
        if (model.role === "user")
            return Qt.rgba(0.31, 0.98, 0.48, 0.1) // Light green
        else if (model.role === "assistant")
            return Qt.rgba(0.55, 0.91, 0.99, 0.1) // Light blue
        else if (model.role === "system")
            return Qt.rgba(1.0, 0.72, 0.42, 0.1)  // Light orange
        else
            return Qt.rgba(0.27, 0.27, 0.35, 0.1) // Default gray
    }
    radius: 8

    // Properties from parent ListView's model
    property string messageRole: model.role || ""
    property string messageContent: model.content || ""
    property string messageTimestamp: model.timestamp || ""
    property var messageAttachments: model.attachments || []

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // Header with role icon, name and timestamp
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                id: roleLabel
                text: {
                    if (messageRole === "user") return "👤 You:"
                    else if (messageRole === "assistant") return "🤖 Assistant:"
                    else if (messageRole === "system") return "🔧 System:"
                    else return messageRole + ":"
                }
                color: {
                    if (messageRole === "user") return "#50FA7B" // Green
                    else if (messageRole === "assistant") return "#8BE9FD" // Blue
                    else if (messageRole === "system") return "#FFB86C" // Orange
                    else return "#F8F8F2" // Default light
                }
                font.bold: true
            }

            Text {
                id: timestampLabel
                text: formatTimestamp(messageTimestamp)
                color: "#F8F8F2"
                opacity: 0.6
                font.pixelSize: 10
                horizontalAlignment: Text.AlignRight
                Layout.fillWidth: true
            }
        }

        // Message content with rich text/markdown support
        Text {
            id: contentText
            text: formatMarkdown(messageContent)
            color: "#F8F8F2"
            wrapMode: Text.WordWrap
            textFormat: Text.RichText
            Layout.fillWidth: true
            onLinkActivated: (link) => Qt.openUrlExternally(link)
        }

        // File attachments section (if any)
        ListView {
            id: attachmentsView
            visible: messageAttachments && messageAttachments.length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? contentHeight : 0
            implicitHeight: contentHeight
            model: messageAttachments
            spacing: 4
            interactive: false

            delegate: Rectangle {
                width: attachmentsView.width
                height: 30
                color: "#6272A4" // Accent color
                radius: 4

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 4
                    spacing: 4

                    Text {
                        text: "📎 " + modelData.fileName + " (" + modelData.fileSize + ", " + modelData.tokenCount + " tokens)"
                        color: "#F8F8F2"
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }

    // Helper functions
    function formatTimestamp(timestamp) {
        if (!timestamp) return ""

        const date = new Date(timestamp)
        const now = new Date()
        const diffMs = now - date
        const diffMins = Math.floor(diffMs / 60000)
        const diffHours = Math.floor(diffMins / 60)
        const diffDays = Math.floor(diffHours / 24)

        if (diffMins < 1) {
            return "just now"
        } else if (diffMins < 60) {
            return diffMins + " min ago"
        } else if (diffHours < 24) {
            return diffHours + " hr ago"
        } else if (diffDays < 7) {
            return diffDays + " day" + (diffDays > 1 ? "s" : "") + " ago"
        } else {
            return date.toLocaleDateString()
        }
    }

    function formatMarkdown(text) {
        if (!text) return ""

        // Convert code blocks with language
        text = text.replace(/```(\w+)?\n([\s\S]*?)\n```/g, function(match, lang, code) {
            return '<pre style="background-color:#2d2d2d; color:#f8f8f2; padding:10px; border-radius:5px; overflow:auto;">' +
                   code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>'
        })

        // Convert inline code
        text = text.replace(/`([^`]+)`/g, '<code style="background-color:#2d2d2d; padding:2px 4px; border-radius:3px;">$1</code>')

        // Convert bold
        text = text.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
        text = text.replace(/__([^_]+)__/g, '<b>$1</b>')

        // Convert italic
        text = text.replace(/\*([^*]+)\*/g, '<i>$1</i>')
        text = text.replace(/_([^_]+)_/g, '<i>$1</i>')

        // Convert headers
        text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>')
        text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>')
        text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>')

        // Convert lists
        text = text.replace(/^- (.+)$/gm, '• $1<br>')
        text = text.replace(/^\* (.+)$/gm, '• $1<br>')
        text = text.replace(/^(\d+)\. (.+)$/gm, '$1. $2<br>')

        // Convert links
        text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color: #8BE9FD;">$1</a>')

        // Convert newlines
        text = text.replace(/\n/g, '<br>')

        return text
    }
}