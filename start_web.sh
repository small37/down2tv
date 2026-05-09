#!/bin/bash

# MediaHub Web 服务快速启动脚本

echo "🚀 MediaHub Web 服务启动"
echo "════════════════════════════"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔄 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📦 安装依赖..."
pip install -r requirements.txt -q

# 创建movie目录
if [ ! -d "movie" ]; then
    echo "📁 创建movie目录..."
    mkdir -p movie
fi

# 启动服务
echo "════════════════════════════"
echo "✅ 启动 Web 服务..."
echo "📍 访问地址: http://localhost:5000"
echo "📁 视频目录: $(pwd)/movie"
echo "🛑 按 Ctrl+C 停止服务"
echo "════════════════════════════"
echo ""

python index.py
