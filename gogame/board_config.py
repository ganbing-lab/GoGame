"""
自定义棋盘配置：从 JSON 文件加载棋盘定义。
格式: {"name": "...", "size": 19, "disabled": [[r,c], ...]}
"""

import json
import os


class BoardConfig:
    """棋盘配置容器"""

    def __init__(self, name: str, size: int, disabled: set):
        self.name = name
        self.size = size
        self.disabled = disabled  # set of (r, c)

    @property
    def is_standard(self):
        return len(self.disabled) == 0

    @staticmethod
    def load(path: str) -> "BoardConfig":
        """从 JSON 文件加载棋盘配置。抛出异常时由调用方处理。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        name = data.get("name", "自定义棋盘")
        size = int(data.get("size", 19))
        disabled_list = data.get("disabled", [])
        disabled = set()
        for item in disabled_list:
            r, c = item[0], item[1]
            if not (0 <= r < size and 0 <= c < size):
                raise ValueError(f"禁用格 ({r},{c}) 超出 {size}×{size} 棋盘范围")
            disabled.add((r, c))

        return BoardConfig(name, size, disabled)


# 默认标准棋盘
STANDARD_CONFIG = BoardConfig("19路标准棋盘", 19, set())
