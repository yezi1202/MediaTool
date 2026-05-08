FROM python:3.9-slim

WORKDIR /app

# Cài đặt các thư viện cần thiết cho hệ thống (nếu có yêu cầu từ crawler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements và cài đặt thư viện Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Dự án chạy trên cổng 5000 theo README
EXPOSE 5000

# Chạy ứng dụng bằng python3 main.py
CMD ["python3", "main.py"]