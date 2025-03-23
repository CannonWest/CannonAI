// src/views/qml/utils/PythonBridge.qml

pragma Singleton
import QtQuick 2.15

/**
 * Singleton object that provides helpers for QML-Python communication
 * This object makes it easier to call Python methods and handle Python signals
 */
QtObject {
    id: pythonBridge

    // Reference to the bridge object (set from Python)
    property var bridge: null

    // Signal for error reporting
    signal errorOccurred(string errorType, string errorMessage)

    // Connection status
    property bool isConnected: bridge !== null

    // Connect to the bridge's error signal
    Component.onCompleted: {
        // Check if bridge was set
        if (typeof bridge !== "undefined" && bridge !== null) {
            // Connect to bridge signals
            bridge.errorOccurred.connect(onBridgeError)

            // Log successful connection
            log("PythonBridge connected successfully")
        } else {
            console.error("PythonBridge: bridge object not set")
        }
    }

    /**
     * Call Python logging
     * @param {string} message - Message to log
     */
    function log(message) {
        if (isConnected) {
            bridge.log_from_qml(message)
        } else {
            console.log("Python bridge not connected: " + message)
        }
    }

    /**
     * Call Python error logging
     * @param {string} errorType - Type of error
     * @param {string} message - Error message
     */
    function logError(errorType, message) {
        if (isConnected) {
            bridge.log_error_from_qml(errorType, message)
        } else {
            console.error("Python bridge not connected. Error: " + errorType + " - " + message)
        }

        // Emit error signal
        errorOccurred(errorType, message)
    }

    /**
     * Handle errors from the bridge
     * @param {string} errorType - Type of error
     * @param {string} message - Error message
     */
    function onBridgeError(errorType, message) {
        console.error("Bridge error: " + errorType + " - " + message)
        errorOccurred(errorType, message)
    }

    /**
     * Format data for sending to Python
     * This helps ensure data is properly structured for Python
     * @param {object} data - Data to format
     * @return {object} Formatted data
     */
    function formatData(data) {
        // Clone the data to avoid modifying the original
        let result = JSON.parse(JSON.stringify(data))

        // Convert JavaScript Date objects to ISO string format
        function convertDates(obj) {
            for (let key in obj) {
                if (obj[key] instanceof Date) {
                    obj[key] = obj[key].toISOString()
                } else if (typeof obj[key] === "object" && obj[key] !== null) {
                    convertDates(obj[key])
                }
            }
        }

        convertDates(result)
        return result
    }

    /**
     * Safe property setter
     * Sets a property on an object, with error handling
     * @param {object} obj - Object to set property on
     * @param {string} propName - Property name
     * @param {any} value - Value to set
     * @return {boolean} Success status
     */
    function safeSetProperty(obj, propName, value) {
        try {
            if (obj && typeof obj.setProperty === "function") {
                obj.setProperty(propName, value)
                return true
            } else if (obj) {
                obj[propName] = value
                return true
            }
            return false
        } catch (e) {
            logError("PropertyError", "Failed to set property " + propName + ": " + e.toString())
            return false
        }
    }

    /**
     * Safe method caller
     * Calls a method on an object, with error handling
     * @param {object} obj - Object to call method on
     * @param {string} methodName - Method name
     * @param {Array} args - Arguments for the method
     * @return {any} Method result or null on error
     */
    function safeCallMethod(obj, methodName, args) {
        try {
            if (obj && typeof obj[methodName] === "function") {
                return obj[methodName].apply(obj, args || [])
            }
            logError("MethodError", "Method " + methodName + " not found or not a function")
            return null
        } catch (e) {
            logError("MethodError", "Failed to call method " + methodName + ": " + e.toString())
            return null
        }
    }

    /**
     * Convert a file URL to a path that Python can use
     * @param {url} fileUrl - QML file URL
     * @return {string} Python-compatible file path
     */
    function fileUrlToPath(fileUrl) {
        let path = fileUrl.toString()

        // Remove the "file:///" prefix
        if (path.startsWith("file:///")) {
            // On Windows, keep the drive letter
            if (Qt.platform.os === "windows") {
                path = path.substring(8) // Remove "file:///"
            } else {
                path = path.substring(7) // Remove "file://"
            }
        } else if (path.startsWith("file://")) {
            path = path.substring(7)
        }

        // Handle URL encoding
        return decodeURIComponent(path)
    }

    /**
     * Format a byte size into a human-readable string
     * @param {number} size - Size in bytes
     * @return {string} Formatted size string
     */
    function formatSize(size) {
        if (size < 1024) {
            return size + " B"
        } else if (size < 1024 * 1024) {
            return (size / 1024).toFixed(1) + " KB"
        } else if (size < 1024 * 1024 * 1024) {
            return (size / (1024 * 1024)).toFixed(1) + " MB"
        } else {
            return (size / (1024 * 1024 * 1024)).toFixed(1) + " GB"
        }
    }

    /**
     * Format a date string into a human-readable string
     * @param {string} dateString - ISO date string
     * @return {string} Formatted date string
     */
    function formatDate(dateString) {
        if (!dateString) return ""

        const date = new Date(dateString)
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
}