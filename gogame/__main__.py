"""
围棋 — 通过 `python -m gogame` 运行。

启动时自动检查 GitHub 更新。连接失败则静默跳过，正常进入游戏。
"""

import sys
import tkinter as tk
from tkinter import messagebox


def main():
    from .updater import check_and_update

    print("[GoGame] 检查更新中...")
    result = check_and_update()

    if result.startswith("updated:"):
        info = result.removeprefix("updated: ")
        print(f"[GoGame] ✅ 已更新: {info}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "GoGame 更新",
            f"已从 GitHub 拉取最新版本！\n\n更新内容: {info}\n\n请重新启动应用以使用新版本。"
        )
        root.destroy()
        sys.exit(0)
    elif result.startswith("up_to_date:"):
        print(f"[GoGame] ✅ 已是最新版本 ({result.removeprefix('up_to_date: ')})")
    elif result.startswith("no_git"):
        print("[GoGame] ⚠ 未检测到 Git 仓库，跳过更新检查。")
    else:
        print(f"[GoGame] ⚠ 更新检查失败（将正常启动）: {result.removeprefix('update_failed: ')}")

    from .app import GoApp
    GoApp().run()


if __name__ == "__main__":
    main()
