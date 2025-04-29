# Data Directory

This directory stores application data files, including:

- SQLite database files (`chat_manager.db`)
- Database journals and write-ahead logs
- Any other persistent data needed by the application

## Important Notes

- Database files in this directory are ignored by git (.gitignore) to prevent data conflicts
- The application expects database files to be located here
- Don't manually modify database files while the application is running
