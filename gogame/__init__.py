"""
围棋 (Go Game) — 双人对弈围棋
===============================
包入口。核心逻辑层 `core` 可独立使用（不依赖 tkinter）。

用法:
    python main.py              # 启动 GUI（含 GitHub 更新检查）
    python -m gogame            # 同上
    from gogame.core import GoGame  # 纯逻辑复用
    from gogame import sgf          # SGF 棋谱导入/导出
    from gogame.updater import check_and_update  # 更新检查
"""

from .core import GoGame
from .board import BoardCanvas
from .app import GoApp
from . import sgf
