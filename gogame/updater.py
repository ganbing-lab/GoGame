"""启动时检查 GitHub 更新。连接失败或任何异常都静默跳过，正常进入游戏。"""

import subprocess
import sys
from pathlib import Path


# 项目根目录（包含 .git 的目录）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str, timeout: float = 15.0) -> subprocess.CompletedProcess | None:
    """在项目根目录执行 git 命令，带超时保护。返回 None 表示执行失败。"""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            # 不弹出命令行窗口 (Windows)
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except Exception:
        return None


def current_version() -> str | None:
    """返回当前的 git 版本标识。失败返回 None。"""
    r = _git("rev-parse", "--short", "HEAD")
    if r and r.returncode == 0:
        return r.stdout.strip()
    return None


def check_and_update() -> str:
    """
    检查 GitHub 是否有新版本，如有则自动更新。

    返回值：
      - "updated: <old> -> <new>"  已更新
      - "up_to_date: <version>"    已是最新
      - "update_failed: <reason>"  连接/更新失败
      - "no_git"                   未检测到 git 或不在 git 仓库中
    """
    # 确认项目根目录存在 .git
    if not (_PROJECT_ROOT / ".git").exists():
        return "no_git"

    # 1. 获取当前版本
    old_version = current_version()
    if old_version is None:
        return "no_git"

    # 2. 从远程拉取最新引用（仅 fetch，不合并）
    r = _git("fetch", "origin", timeout=20.0)
    if r is None or r.returncode != 0:
        return f"update_failed: fetch failed"

    # 3. 比较本地和远程 HEAD
    r_local = _git("rev-parse", "HEAD")
    r_remote = _git("rev-parse", "origin/main")
    if r_local is None or r_remote is None:
        return f"update_failed: rev-parse failed"
    if r_local.returncode != 0 or r_remote.returncode != 0:
        return f"update_failed: rev-parse failed"

    local_sha = r_local.stdout.strip()
    remote_sha = r_remote.stdout.strip()

    if local_sha == remote_sha:
        return f"up_to_date: {old_version}"

    # 4. 有新版本，执行 pull
    r_pull = _git("pull", "origin", "main", timeout=30.0)
    if r_pull is None or r_pull.returncode != 0:
        err = (r_pull.stderr[:80] if r_pull and r_pull.stderr else "unknown") if r_pull else "timeout"
        return f"update_failed: pull error ({err})"

    new_version = current_version() or "unknown"
    return f"updated: {old_version} -> {new_version}"


def check_and_update_verbose(print_func=None):
    """
    带打印的版本，适合在启动时调用。
    print_func 默认为 print，也可传入 logger.info 等。
    """
    if print_func is None:
        print_func = print

    print_func("[GoGame] Checking for updates...")
    result = check_and_update()

    if result.startswith("updated:"):
        print_func(f"[GoGame] Updated: {result.removeprefix('updated: ')}, please restart.")
        return True
    elif result.startswith("up_to_date:"):
        print_func(f"[GoGame] Up to date ({result.removeprefix('up_to_date: ')})")
        return False
    elif result.startswith("no_git"):
        print_func("[GoGame] No git repo found, skipping update check.")
        return False
    else:
        print_func(f"[GoGame] Update check failed: {result.removeprefix('update_failed: ')}")
        return False
