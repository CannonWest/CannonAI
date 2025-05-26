#!/usr/bin/env python3
"""
Gemini Chat GUI Demo

This script demonstrates how to quickly test the Gemini Chat GUI.
It ensures all dependencies are installed and launches the GUI.
"""

import subprocess
import sys
import os
from pathlib import Path

def check_and_install_dependencies():
    """Check if GUI dependencies are installed and install if missing."""
    print("Checking GUI dependencies...")
    
    required_packages = {
        'flask': 'flask>=2.3.0',
        'flask_cors': 'flask-cors>=4.0.0',
        'google.genai': 'google-genai>=0.5.0',
        'tabulate': 'tabulate>=0.9.0',
        'colorama': 'colorama>=0.4.4'
    }
    
    missing_packages = []
    
    for package, install_name in required_packages.items():
        try:
            __import__(package)
            print(f"✓ {package} is installed")
        except ImportError:
            print(f"✗ {package} is NOT installed")
            missing_packages.append(install_name)
    
    if missing_packages:
        print("\nInstalling missing packages...")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', *missing_packages
            ])
            print("\n✓ All dependencies installed successfully!")
        except subprocess.CalledProcessError:
            print("\n✗ Failed to install dependencies. Please install manually:")
            print(f"  pip install {' '.join(missing_packages)}")
            return False
    else:
        print("\n✓ All dependencies are already installed!")
    
    return True

def check_api_key():
    """Check if the Gemini API key is configured."""
    # Check environment variable
    if os.environ.get('GEMINI_API_KEY'):
        print("✓ API key found in environment variable")
        return True
    
    # Check config file
    config_dir = Path(__file__).parent.parent / 'gemini_chat_config'
    config_file = config_dir / 'gemini_chat_config.json'
    
    if config_file.exists():
        print("✓ Configuration file found")
        return True
    
    print("\n⚠ No API key found!")
    print("\nTo set up your API key, you can either:")
    print("1. Set an environment variable:")
    print("   export GEMINI_API_KEY='your-api-key-here'")
    print("\n2. Run the configuration wizard:")
    print("   python gemini_chat/gemini_chat.py --setup")
    print("\n3. Pass it as a command-line argument:")
    print("   python gemini_chat/gemini_chat.py --gui --api-key 'your-api-key-here'")
    
    return False

def launch_gui():
    """Launch the Gemini Chat GUI."""
    print("\n" + "="*60)
    print("LAUNCHING GEMINI CHAT GUI")
    print("="*60 + "\n")
    
    # Get the path to gemini_chat.py
    gemini_chat_path = Path(__file__).parent / 'gemini_chat.py'
    
    if not gemini_chat_path.exists():
        print(f"✗ Error: Could not find {gemini_chat_path}")
        return False
    
    try:
        # Launch the GUI
        subprocess.run([
            sys.executable, 
            str(gemini_chat_path), 
            '--gui'
        ])
        return True
    except KeyboardInterrupt:
        print("\n\nGUI closed by user.")
        return True
    except Exception as e:
        print(f"\n✗ Error launching GUI: {e}")
        return False

def main():
    """Main function to run the GUI demo."""
    print("╔════════════════════════════════════════╗")
    print("║     Gemini Chat GUI Demo Script       ║")
    print("╚════════════════════════════════════════╝\n")
    
    # Check dependencies
    if not check_and_install_dependencies():
        sys.exit(1)
    
    # Check API key
    if not check_api_key():
        response = input("\nDo you want to continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Exiting...")
            sys.exit(0)
    
    # Launch GUI
    print("\nLaunching GUI...")
    print("The GUI will open in your default web browser.")
    print("Press Ctrl+C to stop the server.\n")
    
    if not launch_gui():
        sys.exit(1)
    
    print("\nThank you for using Gemini Chat GUI!")

if __name__ == "__main__":
    main()
