/* ============================================================
 * ui.smoke.js — 页面主流程冒烟测试（模拟浏览器 DOM + 事件）
 * 运行：node docs/tests/ui.smoke.js
 * 覆盖：初始化 → 落子/重复落子 → 悔棋 → 虚手 → 终局 →
 *       计分显示 → 自动死子 → 确认终局 → 新对局 → 切换异形棋盘
 * ============================================================ */
"use strict";

const fs = require("fs");

/* ── 极简 DOM stub（每元素独立事件表 + 可查询 classList） ── */
const elements = {};
function makeEl() {
  const el = {
    _h: {},
    _classes: new Set(),
    addEventListener(t, fn) { el._h[t] = fn; },
    appendChild() {},
    classList: {
      add(c) { el._classes.add(c); },
      remove(c) { el._classes.delete(c); },
      toggle(c) { el._classes.has(c) ? el._classes.delete(c) : el._classes.add(c); },
      contains(c) { return el._classes.has(c); },
    },
    style: {},
    value: "",
    textContent: "",
    innerHTML: "",
    disabled: false,
    width: 0,
    height: 0,
    getContext: () => new Proxy({
      createLinearGradient: () => ({ addColorStop: () => {} }),
      createRadialGradient: () => ({ addColorStop: () => {} }),
    }, { get: (t, k) => (k in t ? t[k] : () => {}) }),
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 800 }),
    files: [],
    click() {},
  };
  return el;
}
global.document = {
  getElementById: (id) => (elements[id] || (elements[id] = makeEl())),
  createElement: () => makeEl(),
};
global.window = { devicePixelRatio: 1 };
global.localStorage = { getItem: () => null, setItem: () => {} };
global.confirm = () => true;
global.addEventListener = () => {};

/* ── 按浏览器顺序加载（末尾追加测试导出） ── */
const code = ["boards.js", "engine.js", "game.js"]
  .map((f) => fs.readFileSync(__dirname + "/../" + f, "utf8"))
  .join("\n");
eval(code + `
;globalThis.__test = {
  get game() { return game; },
  get mode() { return mode; },
  get scoringLocked() { return scoringLocked; },
  get deadSet() { return deadSet; },
};`);
const G = () => __test.game;
const M = () => __test.mode;
const L = () => __test.scoringLocked;
const D = () => __test.deadSet;

let passed = 0, failed = 0;
function ok(name, cond) {
  if (cond) { passed++; console.log("  ✓ " + name); }
  else { failed++; console.error("  ✗ " + name); }
}

/* ── 模拟点击棋盘交叉点（19 路逻辑像素 → 屏幕坐标） ── */
const CELL = 36, MARGIN = 44, PX = MARGIN * 2 + CELL * 18; // 736
function clickAt(r, c) {
  const x = MARGIN + c * CELL, y = MARGIN + r * CELL;
  elements["board"]._h.click({ clientX: x * 800 / PX, clientY: y * 800 / PX });
}
const boardValue = (r, c) => G().board[r][c];
const moveCount = () => G().moves.length;

console.log("═ 页面主流程冒烟测试 ═");

ok("初始化：默认标准 19 路", G().size === 19);
ok("初始化：状态栏显示黑方", elements["turn"].textContent.indexOf("黑方") >= 0);
ok("初始化：计分卡片隐藏", elements["scoring-card"].classList.contains("hidden"));

// 网络检测（无 PeerJS 环境）
elements["btn-net-check"]._h.click();
ok("无 PeerJS 时检测给出提示", elements["net-status"].textContent.indexOf("PeerJS") >= 0);

// 落子
clickAt(3, 3);
ok("黑落子 (3,3)", boardValue(3, 3) === 1 && moveCount() === 1);
clickAt(3, 4);
ok("白落子 (3,4)", boardValue(3, 4) === 2 && moveCount() === 2);
clickAt(4, 3);
ok("黑落子 (4,3)", moveCount() === 3);
clickAt(3, 3);
ok("重复落子被拒绝", moveCount() === 3);
ok("提子计数显示", elements["captures"].textContent.indexOf("提子") >= 0);

// 悔棋
elements["btn-undo"]._h.click();
ok("悔棋：手数回退", moveCount() === 2 && boardValue(4, 3) === 0);
clickAt(4, 3);
ok("重新落子", moveCount() === 3);

// 虚手
elements["btn-pass"]._h.click();
ok("虚手后轮到黑", G().current === 1);
ok("手数状态显示 4/4", elements["move-num"].textContent.indexOf("4 / 4") >= 0);

// 终局 → 计分
elements["btn-end"]._h.click();
ok("终局后进入计分模式", M() === "scoring");
ok("计分卡片显示", !elements["scoring-card"].classList.contains("hidden"));
ok("计分结果包含数目法", elements["scores"].innerHTML.indexOf("数目法") >= 0);
ok("计分结果包含数子法", elements["scores"].innerHTML.indexOf("数子法") >= 0);

// 自动死子检测（空盘不报错）
elements["btn-autodead"]._h.click();
ok("自动死子检测可执行", M() === "scoring");

// 整串死子标记：棋盘有黑(3,3)、白(3,4)、黑(4,3)，其中两个黑子连通
clickAt(3, 3);   // 点击黑(3,3) → 同串黑(4,3) 应一起标记
ok("整串标记死子：两连通黑子同标记", D().has("3,3") && D().has("4,3"));
ok("不相关白子未标记", !D().has("3,4"));
clickAt(4, 3);   // 再点同串任一子 → 整串取消
ok("整串取消：两黑子同取消", !D().has("3,3") && !D().has("4,3"));

// 确认终局
elements["btn-confirm"]._h.click();
ok("确认后锁定", L() === true);
ok("确认按钮变为已确认", elements["btn-confirm"].textContent.indexOf("已确认") >= 0);

// 锁定后返回对局应被拒绝
elements["btn-resume"]._h.click();
ok("锁定后返回对局被拒绝", M() === "scoring");

// 新对局
elements["btn-new"]._h.click();
ok("新对局重置", M() === "playing" && moveCount() === 0 && G().current === 1);
ok("新对局后计分卡片隐藏", elements["scoring-card"].classList.contains("hidden"));

// 切换异形棋盘（迷宫）
elements["board-select"].value = "1";
elements["board-select"]._h.change();
ok("切换到迷宫棋盘", G().name === "迷宫" && G().disabled.size > 0);
ok("棋盘名显示", elements["board-name"].textContent.indexOf("迷宫") >= 0);
// 迷宫上正常落子
clickAt(0, 0);
ok("迷宫棋盘可落子", boardValue(0, 0) === 1 && moveCount() === 1);

console.log("\n" + (failed ? "✗ 存在失败" : "✓ 冒烟测试通过") + "（" + passed + " 通过，失败 " + failed + "）");
process.exitCode = failed ? 1 : 0;
