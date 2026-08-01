#!/bin/bash
# ============================================
# GitHub Actions 环境初始化脚本
# 下载并启动 alist，配置 rclone
# ============================================
set -e

ALIST_VERSION="3.42.0"
ALIST_URL="https://github.com/AlistGo/alist/releases/download/v${ALIST_VERSION}/alist-linux-amd64.tar.gz"
ALIST_DIR="/tmp/alist"

echo "=== 安装 alist ==="
mkdir -p "$ALIST_DIR"
curl -fsSL "$ALIST_URL" -o /tmp/alist.tar.gz
tar -xzf /tmp/alist.tar.gz -C "$ALIST_DIR"
chmod +x "$ALIST_DIR/alist"

echo "=== 生成 alist 配置 ==="
# 用 GitHub Secret 中的 alist 配置覆盖默认配置
mkdir -p "$ALIST_DIR/data"
echo "$ALIST_CONFIG_JSON" > "$ALIST_DIR/data/config.json"

echo "=== 设置 alist 管理员密码 ==="
cd "$ALIST_DIR"
./alist admin set admin  # 重置密码为随机值
# 也可固定密码: ./alist admin set NEW_PASSWORD

echo "=== 启动 alist ==="
nohup ./alist server > /tmp/alist.log 2>&1 &
ALIST_PID=$!
echo "alist PID: $ALIST_PID"

# 等待 alist 启动
sleep 3
if curl -s http://localhost:5244/api/public/settings | head -20; then
    echo "alist 启动成功!"
else
    echo "alist 启动失败, 查看日志:"
    cat /tmp/alist.log
    exit 1
fi

echo "=== 安装 rclone ==="
curl -fsSL https://rclone.org/install.sh | bash

echo "=== 配置 rclone ==="
mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf << 'RCLONE_EOF'
[mcloud]
type = webdav
url = http://localhost:5244/dav
vendor = other
user = admin
pass = admin
RCLONE_EOF

echo "=== 测试 rclone 连接 ==="
rclone lsd mcloud: || echo "警告: rclone 连接测试失败 (可能云盘尚未配置)"

echo "=== 初始化完成 ==="
