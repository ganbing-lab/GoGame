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

## 修复方式（不修改任何配置）

**本仓库已还原为默认配置，未改动任何 git 配置文件。**

需要访问 GitHub 时，在命令前加一次性临时参数即可（只对当次命令生效，不改任何配置）：

```
git -c http.sslBackend=openssl ls-remote origin main        # 例：验证连通
git -c http.sslBackend=openssl push origin main             # 例：推送
```

验证（应返回远端 main 的 commit 号，不再报错）：

```
git -c http.sslBackend=openssl ls-remote origin main
```

> 尊重用户 git 环境：**不要**执行 `git config http.sslBackend openssl`
> （仓库级）或 `git config --global http.sslBackend openssl`（全局）——
> 用户自己还要用 git，配置保持原样。用户如需自行全局修复，命令如下
> （由用户决定，本环境不代改）：

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
