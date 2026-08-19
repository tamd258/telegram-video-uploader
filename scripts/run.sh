#!/bin/bash
# ============================================
# 本地运行脚本
# 下载 Telegram 视频 → 上传到 Google Drive
# ============================================
set -e

echo "============================================"
echo "  Telegram Video Uploader"
echo "  下载 → 上传 Google Drive"
echo "============================================"

# 检查 Google Drive 凭证
if [ ! -f config/gdrive_service_account.json ]; then
    echo "❌ 未找到 Google Drive Service Account JSON"
    echo "   请将 service_account.json 放到 config/gdrive_service_account.json"
    exit 1
fi

# 安装 Python 依赖
pip install --quiet -r requirements.txt

# 运行主程序
python main.py

echo "============================================"
echo "  运行完成"
echo "============================================"
