#!/bin/bash
echo "Installing dependencies..."
pip3 install -r requirements.txt
echo "Dependencies installed."

echo "Starting execution of news_json.py..."
python3 news_json.py
echo "news_json.py execution completed."
