#!/usr/bin/env python3
"""
Test runner script for the OpenAI Chat application.
"""

import os
import sys
import pytest
import argparse
import subprocess


def main():
    """Run tests with specified options."""
    parser = argparse.ArgumentParser(description="Run tests for OpenAI Chat application")

    parser.add_argument(
        "--unit", action="store_true",
        help="Run only unit tests"
    )
    parser.add_argument(
        "--integration", action="store_true",
        help="Run only integration tests"
    )
    parser.add_argument(
        "--api", action="store_true",
        help="Run only API tests"
    )
    parser.add_argument(
        "--ui", action="store_true",
        help="Run only UI tests"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Run all tests"
    )
    parser.add_argument(
        "--coverage", action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--xml", action="store_true",
        help="Generate XML report"
    )
    parser.add_argument(
        "--html", action="store_true",
        help="Generate HTML report (requires pytest-html)"
    )
    parser.add_argument(
        "--pattern", type=str, default=None,
        help="Run tests matching pattern (e.g., 'test_api*')"
    )

    args = parser.parse_args()

    # Set up test arguments
    pytest_args = ["-v", "--tb=short"]

    # Add coverage if requested
    if args.coverage:
        try:
            import pytest_cov
            pytest_args.extend(["--cov=src", "--cov-report=term", "--cov-report=html"])
        except ImportError:
            print("Warning: pytest-cov not installed. Install with 'pip install pytest-cov'.")
            print("Continuing without coverage...")

    # Add XML report if requested
    if args.xml:
        pytest_args.extend(["--junitxml=test-results.xml"])

    # Add HTML report if requested
    if args.html:
        try:
            import pytest_html
            pytest_args.extend(["--html=test-report.html", "--self-contained-html"])
        except ImportError:
            print("Warning: pytest-html not installed. Install with 'pip install pytest-html'.")
            print("Continuing without HTML report...")

    # Determine which tests to run
    test_paths = []

    # Find the project root directory
    # If we're in the tests directory, go up one level
    if os.path.basename(os.getcwd()) == "tests":
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(script_dir)
        # Use current directory for test paths
        test_dir = "."
    else:
        # We're in the project root or elsewhere
        base_dir = os.getcwd()
        test_dir = "tests"

    # Adjust paths based on our location
    if args.unit:
        test_paths.append(os.path.join(test_dir, "unit/") if test_dir != "." else "unit/")

    if args.integration:
        test_paths.append(os.path.join(test_dir, "integration/") if test_dir != "." else "integration/")

    if args.api:
        test_paths.append(os.path.join(test_dir, "api/") if test_dir != "." else "api/")

    if args.ui:
        test_paths.append(os.path.join(test_dir, "ui/") if test_dir != "." else "ui/")

    # If specific types selected but none specified, default to all
    if not test_paths and not args.all and not args.pattern:
        print("No test type specified. Running all tests...")
        args.all = True

    # If --all is specified or no specific type, run all tests
    if args.all:
        if test_dir == ".":
            # We're already in the tests directory
            test_paths = ["."]
        else:
            test_paths = [test_dir]

    # If pattern is specified, find matching tests
    if args.pattern:
        # Find all test files in the tests directory
        import glob

        pattern_files = []
        search_dir = "." if test_dir == "." else test_dir

        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.startswith("test_") and file.endswith(".py") and args.pattern in file:
                    pattern_files.append(os.path.join(root, file))

        if not pattern_files:
            print(f"No tests found matching pattern '{args.pattern}'")
            return 1

        test_paths = pattern_files

    # If no test paths found, exit
    if not test_paths:
        print("No tests found to run")
        return 1

    # Run the tests
    print(f"Running tests: {test_paths}")
    return_code = pytest.main(pytest_args + test_paths)

    # Display summary
    if return_code == 0:
        print("All tests passed!")
    else:
        print(f"Tests failed with return code: {return_code}")

    return return_code


if __name__ == "__main__":
    # Make script executable
    try:
        os.chmod(__file__, 0o755)
    except:
        # Skip if on Windows or permission issues
        pass

    # Ensure pytest is available
    try:
        import pytest
    except ImportError:
        print("Error: pytest not found. Please install with 'pip install pytest'.")
        sys.exit(1)

    # Check for CI environment
    is_ci = os.environ.get('CI', 'false').lower() == 'true'

    try:
        # If running in CI, ensure we have coverage installed
        if is_ci:
            try:
                import pytest_cov
            except ImportError:
                print("Installing pytest-cov for CI environment...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest-cov"])
    except Exception as e:
        print(f"Warning: Failed to install dependencies: {e}")
        print("Continuing with available packages...")

    # Run tests
    sys.exit(main())