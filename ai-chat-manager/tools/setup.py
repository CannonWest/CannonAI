"""
Setup script for initializing the AI Chat Manager project.
"""
import os
import subprocess
import sys
import shutil
import platform

def check_npm_installed():
    """Check if npm is installed and in PATH."""
    try:
        # Try with full path for Windows if common installation
        if platform.system() == "Windows":
            possible_paths = [
                "npm",
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
                        print(f"Found npm at: {npm_path} (version: {result.stdout.decode().strip()})")
                        return npm_path
                except Exception as e:
                    print(f"Attempt with {npm_path} failed: {e}")
                    continue
                    
            print("Could not find npm in common locations.")
            return False
        else:
            # For non-Windows systems
            result = subprocess.run(["npm", "--version"], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, 
                                   check=True)
            print(f"Found npm: version {result.stdout.decode().strip()}")
            return "npm"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"npm check error: {e}")
        return False

def create_env_file():
    """Create .env file from example if it doesn't exist."""
    env_example_path = os.path.join('..', 'backend', '.env.example')
    env_path = os.path.join('..', 'backend', '.env')
    
    if os.path.exists(env_example_path) and not os.path.exists(env_path):
        print("Creating .env file from .env.example...")
        shutil.copy2(env_example_path, env_path)
        print("Please edit the .env file to add your API keys and settings.")
    
def setup_backend():
    """Set up the backend environment."""
    print("\nSetting up backend...")
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 9):
        print("Error: Python 3.9 or higher is required.")
        sys.exit(1)
    
    try:
        # Install dependencies
        print("Installing backend dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "../backend/requirements.txt"],
            check=True
        )
        
        # Create .env file
        create_env_file()
        
        # Initialize database
        print("Initializing database...")
        subprocess.run(
            [sys.executable, "../backend/db_init.py"],
            check=True
        )
        
        print("Backend setup complete.")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"Error during backend setup: {e}")
        return False

def setup_frontend(npm_path):
    """Set up the frontend environment."""
    print("\nSetting up frontend...")
    
    if not npm_path:
        print("Error: npm not found. Please install Node.js and npm first.")
        print("You can download Node.js from: https://nodejs.org/")
        print("After installation, restart this script to continue setup.")
        return False
    
    try:
        # Install dependencies
        print("Installing frontend dependencies...")
        original_dir = os.getcwd()
        os.chdir('../frontend')
        
        print(f"Running npm install using: {npm_path}")
        # Use shell=True for Windows to handle command paths with spaces
        result = subprocess.run(f"{npm_path} install", 
                              shell=True, 
                              check=True,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        print("npm install output:")
        print(result.stdout.decode())
        
        os.chdir(original_dir)
        print("Frontend setup complete.")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error during frontend setup: {e}")
        print(f"stderr: {e.stderr.decode() if hasattr(e, 'stderr') and e.stderr else 'N/A'}")
        os.chdir(original_dir)
        return False
    except Exception as e:
        print(f"Unexpected error during frontend setup: {e}")
        os.chdir(original_dir)
        return False

def main():
    """Run the setup process."""
    print("=== AI Chat Manager Setup ===")
    
    # Ensure we're in the project root
    if not os.path.exists('../backend') or not os.path.exists('../frontend'):
        print("Error: Please run this script from the tools directory.")
        sys.exit(1)
    
    # Check for npm
    npm_path = check_npm_installed()
    
    # Manual npm path override
    if not npm_path:
        print("\nAutomated npm detection failed. You can:")
        print("1. Install Node.js from https://nodejs.org/")
        print("2. Continue with manual npm path entry")
        
        manual_entry = input("\nWould you like to manually specify the npm path? (y/n): ").lower()
        if manual_entry == 'y':
            npm_path = input("Enter full path to npm or npm.cmd: ").strip('"\'')
            # Test the provided path
            try:
                result = subprocess.run(f"{npm_path} --version", 
                                     shell=True, 
                                     check=True,
                                     stdout=subprocess.PIPE)
                print(f"Verified npm: version {result.stdout.decode().strip()}")
            except Exception as e:
                print(f"Failed to execute npm with provided path: {e}")
                npm_path = False
    
    # Set up backend
    backend_success = setup_backend()
    
    # Set up frontend
    frontend_success = False
    if npm_path:
        frontend_success = setup_frontend(npm_path)
    
    print("\n=== Setup Status ===")
    print(f"Backend: {'Success' if backend_success else 'Failed'}")
    print(f"Frontend: {'Success' if frontend_success else 'Failed - npm issues'}")
    
    print("\n=== Next Steps ===")
    if not frontend_success:
        print("For frontend setup:")
        print("1. Make sure Node.js is installed from https://nodejs.org/")
        print("2. Try running frontend setup manually:")
        print("   cd frontend")
        print("   npm install")
        print("3. Or restart this script with administrator privileges")
    else:
        print("To start the application in development mode:")
        print("1. Run the backend: python backend/main.py")
        print("2. Run the frontend: cd frontend && npm run dev")
        print("\nOr use Docker: docker-compose up")

if __name__ == "__main__":
    main()
