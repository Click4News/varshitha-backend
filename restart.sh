#!/bin/bash
echo "開始執行 news_json.py..." >> ~/deployment/restart.log
python3 news_json.py >> ~/deployment/restart.log 2>&1
echo "news_json.py 執行完成。" >> ~/deployment/restart.log
