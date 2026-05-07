#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🌸 MediaTool Trip - Setup & Run${NC}"
echo ""

# Check Python version
echo -e "${YELLOW}[1/5]${NC} Kiểm tra Python..."
if ! command -v python3.12 &> /dev/null; then
    echo -e "${RED}❌ Python3.12 không được cài đặt!${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3.12 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"
echo ""

# Create virtual environment
echo -e "${YELLOW}[2/5]${NC} Tạo virtual environment..."
if [ ! -d "venv" ]; then
    python3.12 -m venv venv
    echo -e "${GREEN}✓ Virtual environment tạo thành công${NC}"
else
    echo -e "${GREEN}✓ Virtual environment đã tồn tại${NC}"
fi
echo ""

# Activate virtual environment
echo -e "${YELLOW}[3/5]${NC} Kích hoạt virtual environment..."
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment kích hoạt${NC}"
echo ""

# Install dependencies
echo -e "${YELLOW}[4/5]${NC} Cài đặt dependencies..."
pip install --upgrade pip setuptools wheel -q
pip install -r requirements.txt -q
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies cài đặt thành công${NC}"
else
    echo -e "${RED}❌ Lỗi cài đặt dependencies!${NC}"
    exit 1
fi
echo ""

# Run application
echo -e "${YELLOW}[5/5]${NC} Khởi động ứng dụng..."
echo -e "${GREEN}✓ Ứng dụng đang chạy...${NC}"
echo ""
echo -e "${GREEN}🚀 Mở trình duyệt: http://localhost:5000${NC}"
echo ""

python3 main.py