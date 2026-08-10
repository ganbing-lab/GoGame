"""
围棋 — 通过 `python -m gogame` 运行。

启动时自动检查 GitHub 更新。连接失败则静默跳过，正常进入游戏。
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# 当通过 pythonw.exe（无控制台）运行时，sys.stdout/stderr 为 None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')


def main():
    from .updater import check_and_update

    print("[GoGame] Checking for updates...")
    result = check_and_update()

    if result.startswith("updated:"):
        info = result.removeprefix("updated: ")
        print(f"[GoGame] Updated: {info}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "GoGame Update",
            f"Updated from GitHub!\n\nChanges: {info}\n\nPlease restart to use the new version."
        )
        root.destroy()
        sys.exit(0)
    elif result.startswith("up_to_date:"):
        print(f"[GoGame] Up to date ({result.removeprefix('up_to_date: ')})")
    elif result.startswith("no_git"):
        print("[GoGame] No git repo found, skipping update check.")
    else:
        print(f"[GoGame] Update check skipped: {result.removeprefix('update_failed: ')}")

    from .app import GoApp
    GoApp().run()


if __name__ == "__main__":
    main()
