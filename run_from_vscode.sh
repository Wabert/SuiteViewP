#!/bin/bash
# Run SuiteView from VSCode - use this in WSL terminal

echo "============================================================"
echo "SuiteView Data Manager - Starting from VSCode"
echo "============================================================"
echo ""

# Check if we're in WSL
if grep -qi microsoft /proc/version; then
    echo "✓ Running in WSL"
else
    echo "⚠ Not running in WSL - this may cause issues"
fi

echo ""

# Activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "❌ Virtual environment not found!"
    echo "Please run: python -m venv venv"
    exit 1
fi

echo ""
echo "Starting SuiteView Data Manager..."
echo "The application window should appear on your Windows desktop."
echo ""

# Run the application
python -m suiteview.main
