#!/bin/bash
echo "Creating virtual environment..."
python3 -m venv venv
echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies in virtual environment..."
pip install -r requirements.txt
echo "Dependencies installed."

echo "Starting execution of news_json.py using virtual environment..."
python news_json.py
echo "news_json.py execution completed."
