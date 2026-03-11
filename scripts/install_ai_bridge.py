#!/usr/bin/env python3
"""
Install the SuiteView AI Bridge VS Code extension.

This script:
1. Checks for Node.js installation
2. Installs npm dependencies
3. Compiles the TypeScript extension
4. Installs the extension in VS Code
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, cwd=None, check=True):
    """Run a command and return the result"""
    print(f"Running: {command}")
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return result


def check_node():
    """Check if Node.js is installed"""
    result = run_command("node --version", check=False)
    if result and result.returncode == 0:
        print(f"Node.js found: {result.stdout.strip()}")
        return True
    
    print("\n" + "=" * 60)
    print("Node.js is required but not found!")
    print("=" * 60)
    print("\nPlease install Node.js from: https://nodejs.org/")
    print("Download the LTS version and run the installer.")
    print("\nAfter installation, restart your terminal and run this script again.")
    print("=" * 60 + "\n")
    return False


def check_npm():
    """Check if npm is installed"""
    result = run_command("npm --version", check=False)
    if result and result.returncode == 0:
        print(f"npm found: {result.stdout.strip()}")
        return True
    return False


def install_extension():
    """Install the VS Code extension"""
    # Get paths
    script_dir = Path(__file__).parent.parent
    extension_dir = script_dir / "vscode-extension" / "suiteview-ai-bridge"
    
    if not extension_dir.exists():
        print(f"Extension directory not found: {extension_dir}")
        return False
    
    print(f"\nExtension directory: {extension_dir}")
    
    # Install npm dependencies
    print("\n--- Installing npm dependencies ---")
    result = run_command("npm install", cwd=extension_dir)
    if not result:
        return False
    
    # Compile TypeScript
    print("\n--- Compiling TypeScript ---")
    result = run_command("npm run compile", cwd=extension_dir)
    if not result:
        print("Compilation failed. Trying alternative approach...")
        result = run_command("npx tsc -p ./", cwd=extension_dir)
        if not result:
            return False
    
    # Install in VS Code
    print("\n--- Installing extension in VS Code ---")
    
    # Find VS Code extensions directory
    if sys.platform == "win32":
        vscode_ext_dir = Path.home() / ".vscode" / "extensions"
    else:
        vscode_ext_dir = Path.home() / ".vscode" / "extensions"
    
    target_dir = vscode_ext_dir / "suiteview.suiteview-ai-bridge-1.0.0"
    
    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy extension files
    import shutil
    
    files_to_copy = ["package.json", "README.md"]
    dirs_to_copy = ["out"]
    
    for f in files_to_copy:
        src = extension_dir / f
        if src.exists():
            shutil.copy2(src, target_dir / f)
            print(f"Copied: {f}")
    
    for d in dirs_to_copy:
        src = extension_dir / d
        dst = target_dir / d
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"Copied: {d}/")
    
    print(f"\nExtension installed to: {target_dir}")
    return True


def main():
    print("=" * 60)
    print("SuiteView AI Bridge - Extension Installer")
    print("=" * 60)
    
    # Check prerequisites
    if not check_node():
        sys.exit(1)
    
    if not check_npm():
        print("npm not found. Please reinstall Node.js.")
        sys.exit(1)
    
    # Install extension
    if install_extension():
        print("\n" + "=" * 60)
        print("SUCCESS! Extension installed.")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart VS Code")
        print("2. The extension will auto-start a server on port 5678")
        print("3. Look for 'SuiteView AI: 5678' in the VS Code status bar")
        print("4. Open SuiteView and click the AI Assistant button!")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("Installation failed. Please check the errors above.")
        print("=" * 60 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
