#!/bin/bash
# GoGame Mac 启动脚本
# 用法: ./mac_start.sh
# 也可以在 Finder 中对 mac_start.sh 右键 → 打开方式 → 终端

set -e
cd "$(dirname "$0")"

echo "================================"
echo "   Go Game - Weiqi / Baduk"
echo "================================"
echo ""

# 1. 尝试 uv（推荐）
if command -v uv &> /dev/null; then
    echo "[INFO] uv found, syncing environment..."
    uv sync --quiet
    echo ""
    uv run python main.py
    exit 0
fi

# 2. 回退：系统 Python
if command -v python3 &> /dev/null; then
    echo "[INFO] Using system Python 3."
    echo ""
    python3 main.py
    exit 0
fi

# 3. 都没有
echo "[ERROR] No Python runtime found."
echo "Install Python 3.10+ from https://www.python.org/downloads/"
echo "Or install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
exit 1
