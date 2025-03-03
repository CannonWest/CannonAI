# src/utils/migration_utils.py

"""
Migration utilities for the OpenAI Chat application.
"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import QMessageBox, QApplication
from PyQt6.QtCore import Qt

from src.utils.logging_utils import get_logger, log_exception
from src.utils import CONVERSATIONS_DIR
from src.models.db_conversation_manager import DBConversationManager

# Get a logger for this module
logger = get_logger(__name__)


def migrate_json_to_db(parent_widget=None):
    """
    Migrate existing JSON conversations to SQLite database
    Returns True if migration was successful or not needed
    """
    db_manager = DBConversationManager()

    try:
        # Check if we have existing JSON files
        if not os.path.exists(CONVERSATIONS_DIR):
            logger.info("No conversations directory found, skipping migration")
            return True

        json_files = [f for f in os.listdir(CONVERSATIONS_DIR) if f.endswith('.json')]

        if not json_files:
            logger.info("No JSON conversation files found, skipping migration")
            return True

        # Confirm migration with user
        if parent_widget:
            result = QMessageBox.question(
                parent_widget,
                "Migration Required",
                f"Found {len(json_files)} JSON conversation files that need to be migrated to the new database format. "
                "This is a one-time operation and will improve application performance.\n\n"
                "Proceed with migration?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if result != QMessageBox.StandardButton.Yes:
                logger.info("User declined migration")
                return False

        # Create progress dialog if in GUI mode
        progress_dialog = None
        if parent_widget:
            from PyQt6.QtWidgets import QProgressDialog

            progress_dialog = QProgressDialog(
                "Migrating conversations to database...",
                "Cancel",
                0,
                len(json_files),
                parent_widget
            )
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)

        # Perform migration
        db_manager.migrate_json_to_db()

        # Close progress dialog
        if progress_dialog:
            progress_dialog.setValue(len(json_files))

        # Show success message
        if parent_widget:
            QMessageBox.information(
                parent_widget,
                "Migration Complete",
                f"Successfully migrated {len(json_files)} conversations to the database."
            )

        # Rename old JSON files as backup
        backup_dir = os.path.join(CONVERSATIONS_DIR, "json_backup")
        os.makedirs(backup_dir, exist_ok=True)

        for filename in json_files:
            src_path = os.path.join(CONVERSATIONS_DIR, filename)
            dst_path = os.path.join(backup_dir, filename)

            try:
                os.rename(src_path, dst_path)
            except Exception as e:
                logger.warning(f"Failed to move {filename} to backup directory: {str(e)}")

        return True

    except Exception as e:
        logger.error("Error during migration")
        log_exception(logger, e, "Migration failed")

        if parent_widget:
            QMessageBox.critical(
                parent_widget,
                "Migration Error",
                f"An error occurred during migration: {str(e)}"
            )

        return False