/* ============================================================
 * net.sync.test.js — 服务器联机集成测试（真实 server.py + 双沙箱）
 * 运行：node docs/tests/net.sync.test.js
 * 覆盖：房主先下棋 → 对方加入 → 完整局面同步 → 双向落子/虚手同步
 *       → 计分/死子标记/确认终局同步 → 无效房间号错误
 * ============================================================ */
"use strict";

const fs = require("fs");
const vm = require("vm");
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const PORT = 8092;
const BASE = "http://127.0.0.1:" + PORT;

/* ── 启动真实 server.py ── */
const srv = spawn("python", ["server/server.py", "--port", String(PORT)], {
  cwd: ROOT,
  stdio: "ignore",
});

async function waitForHealth(tries = 30) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(BASE + "/api/health");
      if (r.ok) return true;
    } catch (e) { /* not ready */ }
    await sleep(300);
  }
  return false;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ── DOM stub（每元素独立事件表） ── */
function makeEl() {
  const el = {
    _h: {}, _classes: new Set(),
    addEventListener(t, fn) { el._h[t] = fn; },
    appendChild() {},
    classList: {
      add(c) { el._classes.add(c); },
      remove(c) { el._classes.delete(c); },
      toggle(c) { el._classes.has(c) ? el._classes.delete(c) : el._classes.add(c); },
      contains(c) { return el._classes.has(c); },
    },
    style: {}, value: "", textContent: "", innerHTML: "", disabled: false,
    width: 0, height: 0,
    getContext: () => new Proxy({
      createLinearGradient: () => ({ addColorStop: () => {} }),
      createRadialGradient: () => ({ addColorStop: () => {} }),
    }, { get: (t, k) => (k in t ? t[k] : () => {}) }),
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 800 }),
    files: [], click() {},
  };
  return el;
}

function buildSandbox() {
  const elements = {};
  const sandbox = {
    console, JSON, Math, Date, setImmediate, queueMicrotask,
    setTimeout, clearTimeout, fetch,
    document: {
      getElementById: (id) => (elements[id] || (elements[id] = makeEl())),
      createElement: () => makeEl(),
    },
    window: { devicePixelRatio: 1 },
    localStorage: { getItem: () => null, setItem: () => {} },
    confirm: () => true,
    addEventListener: () => {},
  };
  vm.createContext(sandbox);
  return { sandbox, elements };
}

const code = ["boards.js", "engine.js", "game.js"]
  .map((f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8"))
  .join("\n");
const EXPORT = `
;globalThis.__t = {
  get game() { return game; },
  get mode() { return mode; },
  get scoringLocked() { return scoringLocked; },
  get netState() { return netState; },
  get srvRoom() { return srvRoom; },
  get netMyColor() { return netMyColor; },
  get netText() { return netStatusEl.textContent; },
  get deadSet() { return deadSet; },
  setServerUrl(v) { SERVER_URL = v; },
};`;

function loadApp(sb) {
  vm.runInContext(code + EXPORT, sb.sandbox);
  return sb.sandbox.__t;
}

function clickAt(elements, r, c) {
  const CELL = 36, MARGIN = 44, PX = MARGIN * 2 + CELL * 18;
  const x = MARGIN + c * CELL, y = MARGIN + r * CELL;
  elements["board"]._h.click({ clientX: x * 800 / PX, clientY: y * 800 / PX });
}

let passed = 0, failed = 0;
function ok(name, cond, detail) {
  if (cond) { passed++; console.log("  ✓ " + name); }
  else { failed++; console.error("  ✗ " + name + (detail ? "  [" + detail + "]" : "")); }
}

async function main() {
  console.log("═ 服务器联机集成测试（真实 server.py） ═");
  if (!(await waitForHealth())) {
    console.error("✗ 服务器未能启动");
    srv.kill();
    process.exit(1);
  }
  console.log("  ✓ 服务器就绪 " + BASE);

  try {
    const host = buildSandbox();
    const guest = buildSandbox();
    const H = loadApp(host);
    const G = loadApp(guest);
    // 测试中通过输入框设置服务器地址（真实用户也这样做）
    host.elements["server-url"].value = BASE;
    guest.elements["server-url"].value = BASE;

    // 1. 房主本地先下 3 手
    clickAt(host.elements, 3, 3);
    clickAt(host.elements, 3, 4);
    clickAt(host.elements, 4, 3);
    ok("房主本地已下 3 手", H.game.moves.length === 3);

    // 2. 房主创建房间
    host.elements["btn-create-room"]._h.click();
    await sleep(600);
    ok("房主创建房间成功", H.netState === "srv" && /^[a-f0-9]{6}$/.test(H.srvRoom), "room=" + H.srvRoom);
    const roomId = H.srvRoom;

    // 3. 创建房间后轮到白（对方），房主（黑）不能越权落子
    clickAt(host.elements, 4, 4);
    await sleep(400);
    ok("轮到对方时房主不能落子", H.game.moves.length === 3);

    // 4. 对方加入
    guest.elements["room-input"].value = roomId;
    guest.elements["btn-do-join"]._h.click();
    await sleep(800);
    ok("对方加入成功", G.netState === "srv");

    // 5. ★ 关键：对方轮询后应看到房主全部棋子 ★
    await sleep(900);
    ok("对方同步看到黑(3,3)", G.game.board[3][3] === 1);
    ok("对方同步看到白(3,4)", G.game.board[3][4] === 2);
    ok("对方同步看到黑(4,3)", G.game.board[4][3] === 1);
    ok("对方手数一致", G.game.moves.length === 3, "moves=" + G.game.moves.length);
    ok("轮到白方（对方执白）", G.game.current === 2);
    ok("双方局面完全一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

    // 6. 对方（白）落子 → 房主同步
    clickAt(guest.elements, 4, 4);
    await sleep(900);
    ok("对方落子后房主同步（白(4,4)）", H.game.board[4][4] === 2 && H.game.moves.length === 4);
    ok("双方仍一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

    // 7. 房主（黑）落子 → 对方同步
    clickAt(host.elements, 5, 5);
    await sleep(900);
    ok("房主落子后对方同步（黑(5,5)）", G.game.board[5][5] === 1 && G.game.moves.length === 5);
    ok("双方仍一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

    // 8. 虚手同步（白虚手）
    guest.elements["btn-pass"]._h.click();
    await sleep(900);
    ok("虚手同步", H.game.moves.length === 6 && H.game.passCount === 1);

    // 9. 双虚终局 → 计分同步（黑虚手）
    host.elements["btn-pass"]._h.click();
    await sleep(900);
    ok("双虚后双方进入计分", H.mode === "scoring" && G.mode === "scoring");

    // 10. 死子标记同步（点黑(3,3)，与(4,3)连通一起标）
    clickAt(host.elements, 3, 3);
    await sleep(900);
    ok("房主标记整串死子", H.deadSet.has("3,3") && H.deadSet.has("4,3"));
    ok("对方死子标记同步", G.deadSet.has("3,3") && G.deadSet.has("4,3"));
    ok("双方 deadSet 一致", JSON.stringify([...H.deadSet].sort()) === JSON.stringify([...G.deadSet].sort()));

    // 11. 确认终局同步
    host.elements["btn-confirm"]._h.click();
    await sleep(900);
    ok("确认终局后双方锁定", H.scoringLocked === true && G.scoringLocked === true);

    // 12. 无效房间号（格式合法但房间不存在）
    const g2sb = buildSandbox();
    const g2 = loadApp(g2sb);
    g2sb.elements["server-url"].value = BASE;
    g2sb.elements["room-input"].value = "abcdef";
    g2sb.elements["btn-do-join"]._h.click();
    await sleep(700);
    ok("无效房间号给出错误提示", g2.netText.indexOf("房间不存在") >= 0, "text=" + g2.netText);
    ok("无效房间号后回到本地模式", g2.netState === "local");
  } finally {
    srv.kill();
  }

  console.log("\n" + (failed ? "✗ 存在失败" : "✓ 服务器联机集成测试通过") + "（" + passed + " 通过，失败 " + failed + "）");
  process.exit(failed ? 1 : 0);
}

main();
