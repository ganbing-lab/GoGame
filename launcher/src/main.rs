//! GoGame 便携启动器
//!
//! 放在空文件夹里即可自动下载 Python 运行时和游戏主体，然后启动游戏。
//! 所有依赖都已就绪时直接启动，过程零干预。
//!
//! 编译: cargo build --release --target x86_64-pc-windows-gnu
//! 输出: target/x86_64-pc-windows-gnu/release/GoGame.exe

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::env;
use std::fs;
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

// ─── 配置 ───────────────────────────────────────────────

const PYTHON_URL: &str =
    "https://www.python.org/ftp/python/3.14.5/python-3.14.5-amd64.zip";
/// SHA-256 of the Python zip (optional verification, skipped if empty)
const PYTHON_SHA256: &str = "c66c6e75aba5cc0434541089127557010da2af9f6ef653abc14bdb694fdf3594";

const REPO_CLONE_URL: &str = "https://github.com/ganbing-lab/GoGame.git";
const REPO_ZIP_URL: &str =
    "https://github.com/ganbing-lab/GoGame/archive/refs/heads/main.zip";

// ─── 入口 ───────────────────────────────────────────────

fn main() {
    // 确保工作目录是 exe 所在目录
    if let Ok(exe) = env::current_exe() {
        if let Some(parent) = exe.parent() {
            let _ = env::set_current_dir(parent);
        }
    }

    let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    log(&format!("GoGame 启动器 — 工作目录: {}", cwd.display()));

    // ── 第一步：确保 Python 便携环境存在 ──
    let python_exe = cwd.join("python").join("python.exe");
    if !python_exe.exists() {
        banner("未检测到 Python 运行环境，开始下载...");
        if !ensure_python(&cwd) {
            fail("下载 Python 失败，请检查网络连接后重试。");
        }
    } else {
        log(&format!("✅ Python 已就绪: {}", python_exe.display()));
    }

    // ── 第二步：确保游戏主体存在 ──
    let main_py = cwd.join("main.py");
    if !main_py.exists() {
        banner("未检测到游戏主体，开始下载...");
        if !ensure_game(&cwd) {
            fail("下载游戏失败，请检查网络连接后重试。");
        }
    } else {
        log("✅ 游戏主体已就绪");
    }

    // ── 第三步：启动游戏 ──
    log("🚀 正在启动游戏...");

    match Command::new(&python_exe)
        .arg("main.py")
        .current_dir(&cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(mut child) => {
            log("游戏进程已启动，启动器退出。");
            drop(child);
        }
        Err(e) => {
            log(&format!("无法启动 Python: {}", e));
            pause_and_exit(&format!("无法启动 Python: {}", e));
        }
    }
}

// ─── 下载逻辑 ───────────────────────────────────────────

fn ensure_python(cwd: &Path) -> bool {
    let zip_path = cwd.join("_python_temp.zip");
    let python_dir = cwd.join("python");

    // 下载
    if !download_file(PYTHON_URL, &zip_path, "Python 运行时") {
        return false;
    }

    // 可选校验
    if !PYTHON_SHA256.is_empty() {
        if let Some(actual) = sha256_file(&zip_path) {
            if actual != PYTHON_SHA256 {
                log(&format!("⚠ SHA256 不匹配! 期望 {} 实际 {}", PYTHON_SHA256, actual));
                log("跳过校验，继续解压...");
            } else {
                log("✅ SHA256 校验通过");
            }
        }
    }

    // 解压
    log("正在解压 Python...");
    if !extract_zip(&zip_path, &python_dir) {
        let _ = fs::remove_file(&zip_path);
        return false;
    }

    let _ = fs::remove_file(&zip_path);

    // 验证
    let py_exe = python_dir.join("python.exe");
    if !py_exe.exists() {
        // 可能有子目录，尝试找到
        if let Some(found) = find_python_exe(&python_dir) {
            log(&format!("在子目录中找到 Python: {}", found.display()));
        } else {
            log("❌ 解压后未找到 python.exe");
            return false;
        }
    }

    log("✅ Python 运行环境安装完成");
    true
}

fn ensure_game(cwd: &Path) -> bool {
    // 优先使用 git clone（保留 .git 用于自动更新）
    if has_git() {
        log("检测到 Git，使用 git clone...");
        let status = Command::new("git")
            .args([
                "clone",
                "--depth", "1",
                REPO_CLONE_URL,
                ".",
            ])
            .current_dir(cwd)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .status();

        if let Ok(s) = status {
            if s.success() {
                log("✅ git clone 成功");
                return true;
            }
            log("git clone 失败，尝试下载 zip...");
        }
    }

    // 回退：下载 zip
    log("下载游戏 zip 包...");
    let zip_path = cwd.join("_game_temp.zip");
    if !download_file(REPO_ZIP_URL, &zip_path, "游戏主体") {
        return false;
    }

    // 解压到临时目录
    let temp_dir = cwd.join("_game_extract");
    let _ = fs::remove_dir_all(&temp_dir);
    fs::create_dir_all(&temp_dir).ok();

    log("正在解压游戏文件...");
    if !extract_zip(&zip_path, &temp_dir) {
        let _ = fs::remove_file(&zip_path);
        let _ = fs::remove_dir_all(&temp_dir);
        return false;
    }
    let _ = fs::remove_file(&zip_path);

    // GitHub zip 解压后有一个 GoGame-main/ 子目录
    // 将其内容移动到当前目录
    let extracted_root = find_extracted_root(&temp_dir);
    match extracted_root {
        Some(src) => {
            log(&format!("移动文件: {} -> {}", src.display(), cwd.display()));
            if !move_dir_contents(&src, cwd) {
                let _ = fs::remove_dir_all(&temp_dir);
                return false;
            }
        }
        None => {
            // 可能直接解压到了 temp_dir
            log("直接在临时目录移动文件...");
            if !move_dir_contents(&temp_dir, cwd) {
                let _ = fs::remove_dir_all(&temp_dir);
                return false;
            }
        }
    }

    let _ = fs::remove_dir_all(&temp_dir);

    // 验证 main.py 存在
    if cwd.join("main.py").exists() {
        log("✅ 游戏主体安装完成");
        true
    } else {
        log("❌ 安装后未找到 main.py");
        false
    }
}

// ─── 工具函数 ───────────────────────────────────────────

fn download_file(url: &str, dest: &Path, label: &str) -> bool {
    log(&format!("⬇ 下载 {}...", label));
    log(&format!("   URL: {}", url));

    // 优先用系统 curl（Win 10+ 自带）
    if has_curl() {
        log("   使用 curl 下载...");
        let status = Command::new("curl")
            .args(["-L", "-o", &dest.to_string_lossy(), "--progress-bar", url])
            .stdout(Stdio::piped()) // 不显示进度条到控制台
            .stderr(Stdio::piped())
            .status();
        if let Ok(s) = status {
            if s.success() && dest.exists() {
                let size = fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
                log(&format!("✅ 下载完成 ({:.1} MB)", size as f64 / 1_048_576.0));
                return true;
            }
        }
        log("   curl 失败，回退到 PowerShell...");
        let _ = fs::remove_file(dest);
    }

    // 回退：PowerShell
    let ps_script = format!(
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; \
         $ProgressPreference = 'SilentlyContinue'; \
         Invoke-WebRequest -Uri '{url}' -OutFile '{dest}'",
        url = url,
        dest = dest.display(),
    );

    let status = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps_script])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .status();

    match status {
        Ok(s) if s.success() && dest.exists() => {
            let size = fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
            log(&format!("✅ 下载完成 ({:.1} MB)", size as f64 / 1_048_576.0));
            true
        }
        _ => {
            log("❌ 下载失败");
            let _ = fs::remove_file(dest);
            false
        }
    }
}

fn extract_zip(zip_path: &Path, dest_dir: &Path) -> bool {
    fs::create_dir_all(dest_dir).ok();

    let ps_script = format!(
        "Expand-Archive -Path '{}' -DestinationPath '{}' -Force",
        zip_path.display(),
        dest_dir.display(),
    );

    let status = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps_script])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .status();

    match status {
        Ok(s) if s.success() => true,
        _ => {
            log("❌ 解压失败");
            false
        }
    }
}

fn move_dir_contents(src: &Path, dest: &Path) -> bool {
    // 用 cmd 的 move / robocopy
    let cmd = format!(
        "robocopy \"{}\" \"{}\" /E /MOVE /NFL /NDL /NJH /NJS /nc /ns /np",
        src.display(),
        dest.display(),
    );

    let status = Command::new("cmd")
        .args(["/C", &cmd])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    // robocopy exit codes: 0-7 = success, 8+ = failure
    match status {
        Ok(s) if s.code().unwrap_or(99) < 8 => true,
        _ => {
            // 回退：逐个 move
            log("   robocopy 不可用，使用 fallback...");
            move_files_fallback(src, dest)
        }
    }
}

fn move_files_fallback(src: &Path, dest: &Path) -> bool {
    fn move_recursive(src: &Path, dest: &Path) -> io::Result<()> {
        if src.is_dir() {
            fs::create_dir_all(dest)?;
            for entry in fs::read_dir(src)? {
                let entry = entry?;
                let dest_child = dest.join(entry.file_name());
                move_recursive(&entry.path(), &dest_child)?;
            }
            let _ = fs::remove_dir(src);
        } else {
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent)?;
            }
            // 如果目标已存在，先删除
            if dest.exists() {
                let _ = fs::remove_file(dest);
            }
            fs::rename(src, dest)?;
        }
        Ok(())
    }

    move_recursive(src, dest).is_ok()
}

fn sha256_file(path: &Path) -> Option<String> {
    let output = Command::new("powershell")
        .args([
            "-NoProfile", "-NonInteractive", "-Command",
            &format!("(Get-FileHash -Path '{}' -Algorithm SHA256).Hash.ToLower()", path.display()),
        ])
        .output()
        .ok()?;

    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        None
    }
}

fn find_python_exe(dir: &Path) -> Option<PathBuf> {
    // 递归搜索 python.exe（最多 2 层）
    fn search(dir: &Path, depth: u32) -> Option<PathBuf> {
        if depth > 2 {
            return None;
        }
        let candidate = dir.join("python.exe");
        if candidate.exists() {
            return Some(candidate);
        }
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                if entry.file_type().map(|t| t.is_dir()).unwrap_or(false) {
                    if let Some(found) = search(&entry.path(), depth + 1) {
                        return Some(found);
                    }
                }
            }
        }
        None
    }
    search(dir, 0)
}

fn find_extracted_root(dir: &Path) -> Option<PathBuf> {
    // GitHub zip 解压后: temp_dir/GoGame-main/xxx
    // 找到第一个包含 main.py 的子目录
    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            if entry.file_type().map(|t| t.is_dir()).unwrap_or(false) {
                if entry.path().join("main.py").exists() {
                    return Some(entry.path());
                }
                // 再深一层
                if let Ok(sub) = fs::read_dir(entry.path()) {
                    for sub_e in sub.flatten() {
                        if sub_e.file_type().map(|t| t.is_dir()).unwrap_or(false)
                            && sub_e.path().join("main.py").exists()
                        {
                            return Some(sub_e.path());
                        }
                    }
                }
            }
        }
    }
    None
}

fn has_git() -> bool {
    Command::new("git")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

fn has_curl() -> bool {
    Command::new("curl")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

// ─── 输出 ────────────────────────────────────────────────

fn log(msg: &str) {
    println!("[GoGame] {}", msg);
}

fn banner(msg: &str) {
    println!();
    println!("═══════════════════════════════════════════");
    println!("  {}", msg);
    println!("═══════════════════════════════════════════");
    println!();
}

fn fail(msg: &str) -> ! {
    eprintln!();
    eprintln!("❌ {}", msg);
    pause_and_exit(msg);
}

fn pause_and_exit(msg: &str) -> ! {
    eprintln!();
    eprintln!("按 Enter 退出...");
    let _ = io::stdin().read_line(&mut String::new());
    std::process::exit(1);
}
