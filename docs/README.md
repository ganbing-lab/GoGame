# 围棋 GoGame · 网页版

纯静态网页围棋客户端，**双人对弈 / 联机对战**，支持**异形棋盘**。
可直接部署到 GitHub Pages（免费），无需任何服务器。

## 功能

- 完整围棋规则：落子 / 提子 / 自杀禁止 / 打劫（positional superko）
- 虚手（连续两虚终局）、认输、悔棋、翻棋导航（回退 / 前进）
- 终局计分：**自动死子检测** + 手动标记（点击棋子标记死子、点击空点轮换领地归属），
  **数目法（日本）与数子法（中国）双显示**
- **异形棋盘**：内置 9 种异形棋盘（迷宫、十字架、四叶草、回字四角挖空、天元孤岛、
  棋盘碎片、南北分断一门、X 形对角、无中心 9 格），并支持导入自定义棋盘 JSON
- **联机对战**：WebRTC 点对点（PeerJS），创建房间生成 4 位房间号，对方输入即可直连，
  无需注册、无需服务器；房主执黑、加入者执白
- 响应式界面：手机 / 电脑均可玩

## 本地运行

直接双击打开 `index.html` 即可（无需安装任何东西）。

> 联机对战需要联网加载 PeerJS（从 CDN），纯本地双人对弈不依赖网络。

## 项目结构

```
docs/
  index.html    — 页面（样式 + 结构）
  boards.js     — 内置棋盘预设（与仓库 boards/*.json 同格式）
  engine.js     — 规则引擎（纯逻辑，可独立测试）
  game.js       — 绘制 / 交互 / 联机
  tests/        — 引擎单元测试（node docs/tests/engine.test.js）
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

## 部署到 GitHub Pages（免费托管）

GitHub Pages 是 GitHub 提供的**静态网页托管**：把你的网页文件推送到仓库，
GitHub 就自动生成一个 `https://你的用户名.github.io/仓库名/` 的网址。
因为本应用是纯 HTML / JS / CSS（无后端），完全兼容 GitHub Pages。

本仓库已推到 GitHub（`ganbing-lab/GoGame`），`docs/` 目录就是网页版，
启用 Pages 后网址为：`https://ganbing-lab.github.io/GoGame/`

### 方法一：本仓库启用 /docs（推荐，最简单）

1. 把 `docs/` 目录提交并推送到 GitHub 仓库（本仓库已推送过，改完运行
   `./upload_to_github.sh "网页版"` 或手动 `git push`）
2. 打开仓库页面 → 点 **Settings**（设置）
3. 左侧菜单找到 **Pages**（页面）
4. **Source（源）** 选择 **Deploy from a branch（从分支部署）**
5. **Branch（分支）** 选 `main`，文件夹选 `/docs`
6. 点 **Save（保存）**，等 1~2 分钟
7. 访问 `https://ganbing-lab.github.io/GoGame/`

以后每次修改推送后，页面自动更新。

### 方法二：新建独立仓库（只要网页版）

1. 在 GitHub 新建一个仓库（如 `go-game`，Public）
2. 把 `docs/` 里的 4 个文件（`index.html`、`boards.js`、`engine.js`、`game.js`）
   上传到新仓库根目录
3. 仓库 Settings → Pages → Source 选 `main` 分支、`/ (root)` 根目录 → Save
4. 访问 `https://ganbing-lab.github.io/go-game/`

### 方法三：本地直接预览

```bash
cd docs
python -m http.server 8000
# 浏览器打开 http://localhost:8000
```

---

## 联机说明

- 一方点「创建房间」→ 生成 4 位房间号（如 `K3PQ`），把房间号发给对方
- 对方点「加入房间」→ 输入房间号 → 建立点对点连接
- 房主执黑先手，棋盘由房主选择（加入者自动同步）
- **完整局面同步**：无论对方何时加入（包括房主已下了很多手、甚至已进入计分阶段），
  连接建立时都会发送整盘数据包（棋盘 + 全部落子历史 + 计分状态），对方加入即看到完整棋局
- 依赖 PeerJS 公共信令服务器（`0.peerjs.com`）；若你的网络访问不畅，
  可以自建 PeerServer 并把 `game.js` 中的 `new Peer(...)` 换成自定义配置

## 引擎测试

```bash
node docs/tests/engine.test.js
```

覆盖：提子 / 自杀禁止 / 打劫 / 虚手终局 / 翻棋回放 / 异形棋盘边界 / 自动死子检测 / 两种计分法。
