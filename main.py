"""快捷入口 — `python main.py` 或 `python -m gogame`。

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


if __name__ == "__main__":
    try:
        from gogame.updater import check_and_update

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

        from gogame.app import GoApp
        GoApp().run()

    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gogame_crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"GoGame Crash Report\n{'=' * 50}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Executable: {sys.executable}\n")
            f.write(f"cwd: {os.getcwd()}\n\n")
            f.write(traceback.format_exc())

        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "GoGame Crash",
                f"Game failed to start.\n\nDetails written to:\n{log_path}\n\n"
                f"{type(e).__name__}: {e}"
            )
            root.destroy()
        except Exception:
            pass
        sys.exit(1)
