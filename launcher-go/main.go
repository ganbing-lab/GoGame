// GoGame 便携启动器 — 无控制台版
//
// 放在空文件夹里双击即可自动下载 Python 运行时和游戏主体，然后启动游戏。
// 无控制台窗口，出错时弹出 MessageBox。
//
// 编译: GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -ldflags="-s -w -H windowsgui" -o GoGame.exe

package main

import (
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
	"syscall"
	"unicode/utf16"
	"unsafe"
)

const (
	pythonURL    = "https://www.python.org/ftp/python/3.14.5/python-3.14.5-amd64.zip"
	pythonSHA256 = "c66c6e75aba5cc0434541089127557010da2af9f6ef653abc14bdb694fdf3594"
	repoCloneURL = "https://github.com/ganbing-lab/GoGame.git"
	repoZipURL   = "https://github.com/ganbing-lab/GoGame/archive/refs/heads/main.zip"
)

func main() {
	exeDir := exeDir()
	os.Chdir(exeDir)

	// 日志文件
	logFile, _ := os.Create(filepath.Join(exeDir, "gogame_launcher.log"))
	log := func(format string, args ...interface{}) {
		s := fmt.Sprintf(format, args...)
		s = strings.TrimSpace(s)
		if logFile != nil {
			fmt.Fprintln(logFile, "[GoGame]", s)
		}
	}
	log("工作目录: %s", exeDir)

	// ── 第一步：确保 Python ──
	pythonExe := filepath.Join(exeDir, "python", "python.exe")
	if !fileExists(pythonExe) {
		log("未检测到 Python，开始下载...")
		if err := ensurePython(exeDir, log); err != nil {
			log("下载 Python 失败: %v", err)
			if logFile != nil { logFile.Close() }
			msgBox("GoGame 启动器", "下载 Python 运行环境失败。\n\n"+err.Error()+"\n\n请检查网络连接后重试。")
			return
		}
	}

	// ── 第二步：确保游戏 ──
	mainPy := filepath.Join(exeDir, "main.py")
	if !fileExists(mainPy) {
		log("未检测到游戏主体，开始下载...")
		if err := ensureGame(exeDir, log); err != nil {
			log("下载游戏失败: %v", err)
			if logFile != nil { logFile.Close() }
			msgBox("GoGame 启动器", "下载游戏主体失败。\n\n"+err.Error()+"\n\n请检查网络连接后重试。")
			return
		}
	}

	// ── 第三步：启动游戏 ──
	log("启动游戏: %s main.py", pythonExe)

	// 优先 pythonw.exe（无控制台）
	pywExe := filepath.Join(exeDir, "python", "pythonw.exe")
	pyExe := pythonExe
	if fileExists(pywExe) {
		pyExe = pywExe
	}

	cmd := exec.Command(pyExe, "main.py")
	cmd.Dir = exeDir
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

	if err := cmd.Start(); err != nil {
		// 回退到 python.exe
		cmd2 := exec.Command(pythonExe, "main.py")
		cmd2.Dir = exeDir
		if err2 := cmd2.Start(); err2 != nil {
			log("无法启动 Python: %v / %v", err, err2)
			if logFile != nil { logFile.Close() }
			msgBox("GoGame 启动器", "无法启动游戏。\n\n请确认 python\\python.exe 存在且可运行。")
			return
		}
	}

	log("游戏已启动 (PID: %d), 启动器退出", cmd.Process.Pid)
	if logFile != nil { logFile.Close() }
}

// ─── exe 目录 ────────────────────────────────────────────

func exeDir() string {
	exe, err := os.Executable()
	if err != nil {
		return "."
	}
	exe, _ = filepath.EvalSymlinks(exe)
	return filepath.Dir(exe)
}

// ─── 下载 Python ─────────────────────────────────────────

func ensurePython(cwd string, log func(string, ...interface{})) error {
	zipPath := filepath.Join(cwd, "_python_temp.zip")
	pythonDir := filepath.Join(cwd, "python")

	log("下载 Python 3.14.5 便携版 (~28 MB)...")
	if err := downloadFile(pythonURL, zipPath, 120); err != nil {
		return fmt.Errorf("下载失败: %w", err)
	}

	if pythonSHA256 != "" {
		actual, shaErr := sha256File(zipPath)
		if shaErr == nil && actual != "" && actual != pythonSHA256 {
			log("警告: SHA256 不匹配 (期望 %s 实际 %s)，继续", pythonSHA256, actual)
		}
	}

	log("正在解压 Python...")
	if err := extractZip(zipPath, pythonDir); err != nil {
		os.Remove(zipPath)
		return fmt.Errorf("解压失败: %w", err)
	}
	os.Remove(zipPath)

	pyExe := filepath.Join(pythonDir, "python.exe")
	if !fileExists(pyExe) {
		if found := findFile(pythonDir, "python.exe", 2); found != "" {
			parent := filepath.Dir(found)
			log("Python 在子目录 %s，移动中...", parent)
			if err := moveDirContents(parent, pythonDir); err != nil {
				return fmt.Errorf("移动文件失败: %w", err)
			}
		} else {
			return fmt.Errorf("解压后未找到 python.exe")
		}
	}

	log("Python 安装完成")
	return nil
}

// ─── 下载游戏 ───────────────────────────────────────────

func ensureGame(cwd string, log func(string, ...interface{})) error {
	if hasGit() {
		log("使用 git clone...")
		tmpDir := filepath.Join(cwd, "_git_tmp")
		os.RemoveAll(tmpDir)
		cmd := exec.Command("git", "clone", "--depth", "1", repoCloneURL, tmpDir)
		if err := cmd.Run(); err != nil {
			log("git clone 失败: %v，改用 zip", err)
			os.RemoveAll(tmpDir)
		} else {
			if err := moveDirContents(tmpDir, cwd); err != nil {
				os.RemoveAll(tmpDir)
				return fmt.Errorf("移动文件失败: %w", err)
			}
			os.RemoveAll(tmpDir)
			log("git clone 成功")
			return nil
		}
	}

	log("下载 game zip...")
	zipPath := filepath.Join(cwd, "_game_temp.zip")
	if err := downloadFile(repoZipURL, zipPath, 60); err != nil {
		return fmt.Errorf("下载 zip 失败: %w", err)
	}

	tempDir := filepath.Join(cwd, "_game_extract")
	os.RemoveAll(tempDir)
	os.MkdirAll(tempDir, 0755)

	log("解压中...")
	if err := extractZip(zipPath, tempDir); err != nil {
		os.Remove(zipPath)
		os.RemoveAll(tempDir)
		return fmt.Errorf("解压失败: %w", err)
	}
	os.Remove(zipPath)

	src := findSubdirWithFile(tempDir, "main.py")
	if src == "" {
		src = tempDir
	}
	log("移动文件: %s -> %s", src, cwd)
	if err := moveDirContents(src, cwd); err != nil {
		os.RemoveAll(tempDir)
		return fmt.Errorf("移动文件失败: %w", err)
	}
	os.RemoveAll(tempDir)

	if fileExists(filepath.Join(cwd, "main.py")) {
		log("游戏安装完成")
		return nil
	}
	return fmt.Errorf("安装后未找到 main.py")
}

// ─── 网络下载 ────────────────────────────────────────────

func downloadFile(url, dest string, timeoutSec int) error {
	client := &http.Client{Timeout: time.Duration(timeoutSec) * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	f, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.Copy(f, resp.Body)
	return err
}

// ─── 解压 / 文件操作 ────────────────────────────────────

func extractZip(zipPath, destDir string) error {
	os.MkdirAll(destDir, 0755)
	cmd := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command",
		fmt.Sprintf("Expand-Archive -Path '%s' -DestinationPath '%s' -Force", zipPath, destDir))
	return cmd.Run()
}

func moveDirContents(src, dest string) error {
	// 先尝试 copy + delete（比 /MOVE 安全，/MOVE 在 dest 已存在目录时会丢文件）
	// 跳过 python/ 目录（第一步已安装好），跳过 GoGame.exe（用户正在运行的自己）
	skipDirs := map[string]bool{"python": true}

	// robocopy /E（仅复制，不删除源）
	cmd := exec.Command("cmd", "/C",
		fmt.Sprintf(`robocopy "%s" "%s" /E /NFL /NDL /NJH /NJS /nc /ns /np /XD python`, src, dest))
	cmd.Run()

	// 检查 main.py 是否成功到达目标
	if fileExists(filepath.Join(dest, "main.py")) {
		// 成功，清理源目录
		os.RemoveAll(src)
		return nil
	}

	// robocopy 没成功，回退到逐文件移动
	_ = skipDirs // used above in robocopy args
	return moveFilesFallback(src, dest)
}

func moveFilesFallback(src, dest string) error {
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}
	for _, e := range entries {
		srcPath := filepath.Join(src, e.Name())
		destPath := filepath.Join(dest, e.Name())
		if e.IsDir() {
			os.MkdirAll(destPath, 0755)
			moveFilesFallback(srcPath, destPath)
			os.Remove(srcPath)
		} else {
			if fileExists(destPath) {
				os.Remove(destPath)
			}
			os.Rename(srcPath, destPath)
		}
	}
	return nil
}

func sha256File(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	io.Copy(h, f)
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func findFile(dir, name string, maxDepth int) string {
	if maxDepth < 0 {
		return ""
	}
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if e.Name() == name && !e.IsDir() {
			return filepath.Join(dir, name)
		}
		if e.IsDir() {
			if found := findFile(filepath.Join(dir, e.Name()), name, maxDepth-1); found != "" {
				return found
			}
		}
	}
	return ""
}

func findSubdirWithFile(dir, filename string) string {
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		p := filepath.Join(dir, e.Name())
		if fileExists(filepath.Join(p, filename)) {
			return p
		}
		subs, _ := os.ReadDir(p)
		for _, s := range subs {
			if !s.IsDir() {
				continue
			}
			pp := filepath.Join(p, s.Name())
			if fileExists(filepath.Join(pp, filename)) {
				return pp
			}
		}
	}
	return ""
}

func hasGit() bool {
	return exec.Command("git", "--version").Run() == nil
}

// ─── Windows MessageBox ──────────────────────────────────

func msgBox(title, text string) {
	kernel32 := syscall.NewLazyDLL("user32.dll")
	msgBoxW := kernel32.NewProc("MessageBoxW")
	msgBoxW.Call(0,
		uintptr(unsafe.Pointer(toUint16Ptr(text))),
		uintptr(unsafe.Pointer(toUint16Ptr(title))),
		0x00000030) // MB_ICONERROR | MB_OK
}

func toUint16Ptr(s string) *uint16 {
	u := utf16.Encode([]rune(s + "\x00"))
	return &u[0]
}
