# Dockerfile
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 複製相依檔案並安裝依賴
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 複製所有檔案到容器中
COPY . .

# 將容器內的 8080 埠口暴露出來
EXPOSE 8080

# 使用 uvicorn 啟動 FastAPI 應用，並綁定 PORT
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
