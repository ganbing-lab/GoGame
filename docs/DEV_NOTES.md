# 开发环境备忘：git 访问 GitHub 的 TLS 问题

> 给未来的开发者 / AI 会话：**遇到 `schannel: ... SEC_E_NO_CREDENTIALS` 报错时先看这里**，
> 不用重新排查一遍。

## 现象

本机执行 git 访问 HTTPS 仓库（如 `git push` / `git fetch` / `git ls-remote`）时报：

```
fatal: unable to access 'https://github.com/...':
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)
```

## 原因

- 本机 Windows 的 **schannel（默认 TLS 后端）握手失败**，但 TCP/DNS 正常。
- 已确认 **OpenSSL 后端完全正常**（Node.js 走 OpenSSL 可正常访问 https://github.com）。

## 已做的修复

本仓库（E:\GoGame）的 git 配置已切换为 OpenSSL 后端：

```
git config http.sslBackend openssl      # 已写入 E:\GoGame\.git\config
```

验证（应返回远端 main 的 commit 号，不再报错）：

```
git ls-remote origin main
```

## 如需全局修复（在其他目录 / 其他仓库也生效）

在**用户自己的终端**（非沙箱）执行：

```
git config --global http.sslBackend openssl
```

## 附加限制：本自动化环境的 push 认证

- TLS 修复后，**匿名读**（ls-remote / clone 公开仓库）可正常完成。
- **push 需要交互式凭据**（credential.helper=manager 依赖 Windows 凭据管理器，
  沙箱内无法弹出认证），所以自动化环境内 `git push` 仍会失败于认证环节——
  **推送请由用户在正常终端执行**：`./upload_to_github.sh "提交信息"`。

## 线上部署状态（2025-*）

- GitHub Pages 已启用并部署：https://ganbing-lab.github.io/GoGame/
- 部署源：`main` 分支 `/docs` 目录（仓库 Settings → Pages）
- 页面更新时机：push 到 main 后 1~3 分钟，浏览器强刷（Ctrl+F5）可见
