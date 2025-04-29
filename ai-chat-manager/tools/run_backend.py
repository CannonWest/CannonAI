"""
Script to run just the AI Chat Manager backend.
"""
import os
import subprocess
import sys
import webbrowser
import time

def main():
    """Run only the backend server."""
    print("=== AI Chat Manager Backend ===")
    
    # Ensure we're in the project root
    if not os.path.exists('../backend'):
        print("Error: Please run this script from the tools directory.")
        sys.exit(1)
    
    # Change to backend directory and run
    os.chdir('../backend')
    try:
        print("Starting backend server...")
        print("You can access the API docs at: http://127.0.0.1:8000/docs")
        
        # Open the API docs after a delay
        def open_browser():
            time.sleep(2)
            webbrowser.open("http://127.0.0.1:8000/docs")
        
        # Start browser in a separate thread
        import threading
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # Run the server
        subprocess.run([sys.executable, "main.py"], check=True)
    except KeyboardInterrupt:
        print("\nBackend server stopped.")
    finally:
        os.chdir('..')

if __name__ == "__main__":
    main()
