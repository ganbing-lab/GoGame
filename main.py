"""快捷入口 — `python main.py` 或 `python -m gogame`。

启动时自动检查 GitHub 更新。连接失败则静默跳过，正常进入游戏。
"""

import sys
import tkinter as tk
from tkinter import messagebox


if __name__ == "__main__":
    # ── 第一步：检查更新（在任何游戏模块导入之前） ──
    # updater 只依赖 stdlib，可以安全地提前导入
    from gogame.updater import check_and_update

    print("[GoGame] 检查更新中...")
    result = check_and_update()

    if result.startswith("updated:"):
        info = result.removeprefix("updated: ")
        print(f"[GoGame] ✅ 已更新: {info}")
        # 需要弹出对话框提示重启，因为 tkinter 不能热加载已更新的模块
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

    # ── 第二步：正常启动游戏 ──
    from gogame.app import GoApp
    GoApp().run()
