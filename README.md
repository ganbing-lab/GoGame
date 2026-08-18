# 围棋 Go Game

双人对弈围棋，Python + Tkinter 实现。19×19 标准棋盘。

> 另有**网页版**（`docs/` 目录）：纯静态、支持异形棋盘、可联机对战，
> 直接部署到 GitHub Pages 即可在线玩。详见 [docs/README.md](docs/README.md)。

## 启动

```bash
# 方式一：双击（推荐）
start.bat

# 方式二：命令行
python main.py
# 或
python -m gogame
```

依赖只含 Python 自带 `tkinter`。

### 便携运行（无需在目标机器安装 Python）

1. 在本机有 Python 的环境下运行 `setup_portable_python.bat`
2. 脚本会将 Python 解释器完整复制到项目的 `python/` 目录
3. 之后把整个项目文件夹复制到任意 Windows 机器，双击 `start.bat` 即可运行

`start.bat` 会自动按以下优先级寻找 Python：
1. 项目文件夹内的 `python/python.exe`（便携）
2. 系统安装的 `uv`
3. 系统安装的 `python`

---

## 项目结构

```
gogame/
  config.py      — 常量（棋盘尺寸、颜色、贴目等）
  core.py        — 纯逻辑引擎（无 UI 依赖，可独立复用）
  board.py       — 棋盘 Canvas 绘制与鼠标交互
  app.py         — 主窗口、面板、数目交互
  __init__.py    — 包入口，导出 GoGame / BoardCanvas / GoApp
  __main__.py    — `python -m gogame` 入口
main.py          — 快捷启动脚本
start.bat        — Windows 双击启动
pyproject.toml   — uv 项目配置
```

### 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `core.py` | 落子/提子/打劫/气/眼/数目/数子/自动死子检测 | 仅 `config` |
| `board.py` | tkinter Canvas：画棋盘/棋子/星位/死子标记/悬停 | `config`, `core` |
| `app.py` | 主窗口、面板按钮、数目阶段交互 | `config`, `core`, `board` |

`core.GoGame` 完全不依赖 tkinter，可被任何其他前端（Pygame、WebSocket 服务端等）复用。

---

## 规则

### 行棋

- 黑先白后，标准 19×19
- 落子 → 自动提走无气敌子
- 自杀禁止
- **打劫**：不能立刻下出与对手上一手之前完全相同的局面（positional superko，单步）

### 终局与计分

1. 双方各虚手（Pass）一次，或手动点击"终局"
2. 进入数目阶段：
   - **自动点目**检测死子（不能到达边缘 + 眼数 < 2 → 死子）
   - 可手动点击棋子标记/取消死子（红色叉号）
3. 右侧面板同时显示两种计分法：
   - **数目法（日本）**：目 + 提子 + 贴目
   - **数子法（中国）**：活子 + 目 + 提子 + 贴目
4. 白方贴 6.5 目（KOMI）

### 自动死子检测

算法：两轮迭代消除。

**第一轮：边缘可达性**
1. 扫描棋盘所有棋串
2. 从棋串出发穿空点/己子/已判死子 → 能否到达棋盘边缘？
3. 不能到达边缘且独享眼区 < 2 → 判死
4. 把死子视为空地，重复直到稳定（最多 8 轮）

**第二轮：领地感知（补充第一轮漏掉的死子）**
1. 用当前死子集计算领地归属（territory_map）
2. 对于未被第一轮标记的死棋串：检查其所有出口是否都通往对手领地
3. 被对手领地完全封锁 + 眼区 < 2 → 判死
4. 同样迭代消除至稳定

注：双活（seki）仍无法自动处理，需手动调整。

---

## API 示例

```python
from gogame.core import GoGame

g = GoGame()
g.play(3, 3)     # 黑落子，返回提子数（0 表示未提子）
g.play(3, 4)     # 白落子
g.pass_move()    # 黑虚手
g.pass_move()    # 白虚手 → 终局

dead = g.auto_detect_dead_stones()
bj, wj, terr = g.score_japanese(dead)   # 数目法
bc, wc, _, live = g.score_chinese(dead) # 数子法
```

---

## 状态

- [x] 19×19 棋盘 + Tkinter UI
- [x] 落子 / 提子 / 打劫 / 自杀禁止
- [x] 虚手 + 终局流程
- [x] 数目阶段（手动标记死子）
- [x] 自动死子检测（两轮：边缘可达性 + 领地感知）
- [x] 数目法 + 数子法 双重显示
- [x] SGF 棋谱导入/导出
- [x] 翻棋导航（查看历史局面）
- [ ] AI 对手
- [ ] 让子
- [ ] 悔棋
