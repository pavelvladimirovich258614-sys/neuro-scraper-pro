#!/bin/bash

echo "====================================="
echo "  NeuroScraper Pro Bot Launcher"
echo "====================================="
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo ""
    echo "Installing dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo ""
echo "Starting bot..."
echo ""
python main.py
