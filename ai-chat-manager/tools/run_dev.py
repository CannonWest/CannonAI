"""
Script to run the AI Chat Manager in development mode.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
import platform
import logging

# Set up a basic logger
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[
                       logging.StreamHandler(sys.stdout),
                       logging.FileHandler(os.path.join(os.path.dirname(__file__), 'dev.log'))
                   ])

logger = logging.getLogger('dev_runner')

def check_npm_path():
    """Find correct npm executable path."""
    # Try with full path for Windows if common installation
    if platform.system() == "Windows":
        possible_paths = [
            "npm",  # Try PATH first
            "npm.cmd",  # Windows sometimes needs .cmd extension
            r"C:\Program Files\nodejs\npm.cmd",
            r"C:\Program Files (x86)\nodejs\npm.cmd",
            os.path.expanduser(r"~\AppData\Roaming\npm\npm.cmd")
        ]
        
        # Try each possible path
        for npm_path in possible_paths:
            try:
                result = subprocess.run([npm_path, "--version"], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE, 
                                     check=False,
                                     shell=True)
                if result.returncode == 0:
                    logger.info(f"Found npm at: {npm_path} (version: {result.stdout.decode().strip()})")
                    return npm_path
            except Exception:
                continue
                
        logger.error("Could not find npm in common locations. Please make sure Node.js is installed.")
        return None
    else:
        # For non-Windows systems
        return "npm"

def run_backend():
    """Run the backend server."""
    logger.info("Starting backend server...")
    os.chdir('../backend')
    
    # Create a modified environment with PYTHONPATH set to include the backend directory
    env = os.environ.copy()
    backend_dir = os.path.abspath('.')
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{backend_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = backend_dir
    
    logger.info(f"Setting PYTHONPATH to include: {backend_dir}")
    
    try:
        subprocess.run([sys.executable, "main.py"], check=True, env=env)
    except KeyboardInterrupt:
        logger.info("Backend server stopped.")
    finally:
        os.chdir('../tools')

def run_frontend(npm_path):
    """Run the frontend development server."""
    if not npm_path:
        logger.error("ERROR: npm not found. Frontend server cannot start.")
        return
        
    logger.info("Starting frontend development server...")
    os.chdir('../frontend')
    try:
        # Use shell=True for Windows to handle command paths with spaces
        subprocess.run(f"{npm_path} run dev", shell=True, check=True)
    except KeyboardInterrupt:
        logger.info("Frontend server stopped.")
    finally:
        os.chdir('../tools')

def open_browser():
    """Open the web browser after a delay."""
    time.sleep(5)  # Wait for servers to start
    webbrowser.open("http://localhost:3000")

def main():
    """Run both backend and frontend servers."""
    logger.info("=== AI Chat Manager Development Mode ===")
    
    # Ensure we're in the project root
    if not os.path.exists('../backend') or not os.path.exists('../frontend'):
        logger.error("Error: Please run this script from the tools directory.")
        sys.exit(1)
    
    # Find npm path
    npm_path = check_npm_path()
    
    # Create and start threads
    backend_thread = threading.Thread(target=run_backend)
    frontend_thread = threading.Thread(target=run_frontend, args=(npm_path,))
    browser_thread = threading.Thread(target=open_browser)
    
    # Start servers
    backend_thread.start()
    time.sleep(2)  # Give backend a head start
    
    if npm_path:
        frontend_thread.start()
        browser_thread.start()
    else:
        logger.warning("WARNING: Frontend server not started due to missing npm.")
        logger.info("You can manually start the frontend with:")
        logger.info("  cd frontend")
        logger.info("  npm run dev")
    
    # Keep the main thread running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nShutting down servers...")
        logger.info("Press Ctrl+C again in the server terminals to exit completely.")

if __name__ == "__main__":
    main()
