#!/usr/bin/env python3
"""
Build script for the Gemini Chat React frontend

This script handles the building of the React frontend for the web-based UI.
It installs dependencies and runs the build process.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Build the Gemini Chat React frontend")
    parser.add_argument('--dev', action='store_true', help='Run development server instead of building')
    parser.add_argument('--clean', action='store_true', help='Clean build directory before building')
    return parser.parse_args()


def get_frontend_dir():
    """Get the path to the frontend directory"""
    # Get the directory of this script
    script_dir = Path(__file__).resolve().parent
    
    # Frontend directory is ui/frontend
    frontend_dir = script_dir / "ui" / "frontend"
    
    if not frontend_dir.exists():
        print(f"Error: Frontend directory not found at {frontend_dir}")
        sys.exit(1)
    
    return frontend_dir


def check_npm():
    """Check if npm is installed"""
    try:
        subprocess.run(["C:\\Program Files\\nodejs\\npm", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def clean_build(frontend_dir):
    """Clean build directory"""
    build_dir = frontend_dir / "build"
    if build_dir.exists():
        print(f"Cleaning build directory: {build_dir}")
        # On Windows, some files might be locked, so we need to handle errors
        try:
            import shutil
            shutil.rmtree(build_dir)
        except PermissionError:
            print("Warning: Could not remove some files due to permission error")
        except Exception as e:
            print(f"Warning: {e}")


def install_dependencies(frontend_dir):
    """Install dependencies with npm"""
    print(f"Installing dependencies in {frontend_dir}")
    result = subprocess.run(
        ["C:\\Program Files\\nodejs\\npm", "install"],
        cwd=frontend_dir,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error installing dependencies: {result.stderr}")
        sys.exit(1)
    
    print("Dependencies installed successfully")


def build_frontend(frontend_dir):
    """Build the frontend"""
    print(f"Building frontend in {frontend_dir}")
    result = subprocess.run(
        ["C:\\Program Files\\nodejs\\npm", "run", "build"],
        cwd=frontend_dir,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error building frontend: {result.stderr}")
        sys.exit(1)
    
    print("Frontend built successfully")
    
    # Verify build directory exists
    build_dir = frontend_dir / "build"
    if not build_dir.exists():
        print(f"Error: Build directory not found at {build_dir}")
        sys.exit(1)
    
    print(f"Build output available at: {build_dir}")
    return build_dir


def run_dev_server(frontend_dir):
    """Run the development server"""
    print(f"Starting development server for {frontend_dir}")
    try:
        # This will block until Ctrl+C
        subprocess.run(
            ["C:\\Program Files\\nodejs\\npm", "start"],
            cwd=frontend_dir
        )
    except KeyboardInterrupt:
        print("\nDevelopment server stopped")


def main():
    """Main entry point"""
    args = parse_args()
    
    # Check if npm is installed
    if not check_npm():
        print("Error: npm is not installed. Please install Node.js and npm.")
        sys.exit(1)
    
    # Get frontend directory
    frontend_dir = get_frontend_dir()
    
    # Install dependencies
    install_dependencies(frontend_dir)
    
    # Clean if requested
    if args.clean:
        clean_build(frontend_dir)
    
    # Run dev server or build
    if args.dev:
        run_dev_server(frontend_dir)
    else:
        build_dir = build_frontend(frontend_dir)
        print("\nTo run the web UI, use:")
        print(f"  python gemini_chat.py --web --static-dir {build_dir}")


if __name__ == "__main__":
    main()
