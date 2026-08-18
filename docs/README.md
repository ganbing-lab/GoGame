# 围棋 GoGame · 网页版

网页围棋客户端，**双人对弈 / 服务器联机对战**，支持**异形棋盘**。
页面本身是纯静态，可部署到 GitHub Pages；联机需要一个轻量服务器（`server/server.py`）。

## 功能

- 完整围棋规则：落子 / 提子 / 自杀禁止 / 打劫（positional superko）
- 虚手（连续两虚终局）、认输、悔棋、翻棋导航（回退 / 前进）
- 终局计分：**自动死子检测** + 手动标记（点击棋子**自动选中整个连通棋串**标记死子、
  点击空点轮换领地归属），**数目法（日本）与数子法（中国）双显示**
- **异形棋盘**：内置 9 种异形棋盘（迷宫、十字架、四叶草、回字四角挖空、天元孤岛、
  棋盘碎片、南北分断一门、X 形对角、无中心 9 格），并支持导入自定义棋盘 JSON
- **联机对战（服务器模式）**：房主创建房间生成 6 位房间号，对方输入即可加入；
  服务器只做**状态中继**（规则在两端各跑同一引擎），对局实时全量同步；
  房主执黑、加入者执白
- 响应式界面：手机 / 电脑均可玩

## 本地运行（单机双人）

直接双击打开 `index.html` 即可（无需安装任何东西）。

## 联机对战（推荐：自己电脑跑服务器）

```bash
# 1. 启动服务器（页面与 API 同源，一条命令）
python server/server.py --port 8080

# 2. 浏览器打开 http://<本机IP>:8080/    （本机测试可填 127.0.0.1）
#    其它设备（手机/朋友）填你的局域网 IP，如 http://192.168.1.5:8080
#    服务器地址也可以填在页面「服务器地址」输入框（跨源时填 http://IP:端口）
```

- 房主点「创建房间」→ 得到 6 位房间号，发给对方
- 对方打开页面 → 填服务器地址 → 「加入房间」→ 输入房间号
- **跨公网联机**：如果你有 HTTP 内网穿透（ngrok / cpolar / frp 等），把 8080
  端口穿透出去，把穿透域名填进「服务器地址」即可，任何网络都能加入
- 前端放 GitHub Pages（https）时连穿透域名：需穿透服务支持 HTTPS（多数支持），
  服务器已带 CORS 头，跨源访问没问题

### 内网穿透（natapp 免费版）启动步骤

```bash
# 1. 启动 GoGame 服务器
python server/server.py --port 8080

# 2. 启动 natapp（natapp.cn 注册 → 下载 natapp.exe → 创建免费隧道端口 8080 →
#    同目录新建 natapp.ini：authtoken=你的token）→ 双击运行
#    终端显示 "Tunnel Status: Online" 和域名 xxxx.natappfree.cc

# 3. 把 xxxx.natappfree.cc 填进页面「服务器地址」；对方也用该域名打开页面
```

> ⚠️ natapp 免费隧道每次启动随机分配域名且有使用时长限制，失效就重启 natapp
> 拿新域名（报 `Tunnel not found` 即隧道已失效）。
> 同 WiFi 设备联机不需要穿透，直接用 `http://电脑IP:8080`。

> 服务器只做状态中转（房间 + 最新局面存储），不做规则计算、没有 NAT/穿透问题，
> 手机热点、公司内网等都能稳定联机。房间 1 小时无活动自动清理。

## 项目结构

```
docs/
  index.html    — 页面（样式 + 结构）
  boards.js     — 内置棋盘预设（与仓库 boards/*.json 同格式）
  engine.js     — 规则引擎（纯逻辑，可独立测试）
  game.js       — 绘制 / 交互 / 联机
  tests/        — 测试（引擎 / 页面流程 / 服务器联机集成）
server/
  server.py     — 联机服务器（状态中继 + 托管 docs/ 页面，纯标准库）
```

## 自定义棋盘

导入的 JSON 与仓库 `boards/` 目录同一格式：

```json
{
  "name": "我的棋盘",
  "size": 19,
  "disabled": [[0, 0], [9, 9], [18, 18]]
}
```

- `size`：路数（2 ~ 25）
- `disabled`：禁用的交叉点列表（异形棋盘的"挖空"部分），每项 `[行, 列]`

在页面「棋盘」卡片点击 **导入棋盘 JSON** 选择文件即可使用。

---

## 部署到 GitHub Pages（页面托管）

GitHub Pages 是 GitHub 提供的**静态网页托管**：把你的网页文件推送到仓库，
GitHub 就自动生成一个 `https://你的用户名.github.io/仓库名/` 的网址。

> 注意：GitHub Pages 只托管**页面**。联机对战需要额外的 `server/server.py`
> 服务器（见上文"联机对战"），页面可以放 Pages，服务器放你自己电脑 / 内网穿透。

本仓库已推到 GitHub（`ganbing-lab/GoGame`），`docs/` 目录就是网页版，
启用 Pages 后网址为：`https://ganbing-lab.github.io/GoGame/`

### 启用步骤

1. 把 `docs/` 目录提交并推送到 GitHub 仓库（改完运行 `./upload_to_github.sh "更新"`）
2. 仓库页面 → **Settings** → 左侧 **Pages**
3. **Source** 选 **Deploy from a branch**，分支 `main`，文件夹 `/docs` → **Save**
4. 等 1~2 分钟，访问 `https://ganbing-lab.github.io/GoGame/`

### 本地直接预览

```bash
python -m http.server 8000 --directory docs
# 浏览器打开 http://localhost:8000
```

---

## 引擎与测试

```bash
node docs/tests/engine.test.js      # 规则引擎：提子/自杀/打劫/异形棋盘/计分
node docs/tests/ui.smoke.js         # 页面主流程
node docs/tests/net.sync.test.js    # 服务器联机集成测试（自动起真实 server.py）
```
