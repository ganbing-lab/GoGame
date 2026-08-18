/* ============================================================
 * net.sync.test.js — 联机同步测试（双沙箱 + Mock Peer）
 * 运行：node docs/tests/net.sync.test.js
 * 覆盖：房主先下棋 → 对方加入 → 完整局面同步（历史落子可见）→
 *       后续落子/虚手双向同步 → 计分状态同步
 * ============================================================ */
"use strict";

const fs = require("fs");
const vm = require("vm");

/* ═════════ 网络总线（沙箱外，桥接两端） ═════════ */
class NetBus {
  constructor() { this.hosts = new Map(); }
}

class MockConn {
  constructor() { this._h = {}; this.open = false; this._peer = null; }
  on(t, fn) { this._h[t] = fn; }
  send(data) {
    if (this._peer && this._peer._h.data) {
      setImmediate(() => this._peer._h.data(data));
    }
  }
  _emit(t, arg) {
    if (t === "open") this.open = true;
    if (this._h[t]) this._h[t](arg);
  }
  close() {}
}

function makePeerClass(bus, role) {
  return class MockPeer {
    constructor(id) {
      this._id = id;
      this._h = {};
      this._destroyed = false;
      if (role === "host" && id) bus.hosts.set(id, this);
      setImmediate(() => this._emit("open", id || "guest-" + Math.random()));
    }
    on(t, fn) { this._h[t] = fn; }
    connect(id) {
      const host = bus.hosts.get(id);
      if (!host) {
        // 模拟"找不到该房间"：返回连接并触发 peer-unavailable 错误
        const guestConn = new MockConn();
        setImmediate(() => guestConn._emit("error", { type: "peer-unavailable", message: "Could not find peer " + id }));
        return guestConn;
      }
      const guestConn = new MockConn();
      const hostConn = new MockConn();
      guestConn._peer = hostConn;
      hostConn._peer = guestConn;
      host._emit("connection", hostConn);
      setImmediate(() => { guestConn._emit("open"); hostConn._emit("open"); });
      return guestConn;
    }
    destroy() { this._destroyed = true; }
    _emit(t, arg) { if (this._h[t]) this._h[t](arg); }
  };
}

/* ═════════ DOM stub 工厂 ═════════ */
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

function buildSandbox(bus, role) {
  const elements = {};
  const sandbox = {
    console, JSON, Math, Date, setImmediate, queueMicrotask,
    setTimeout, clearTimeout,
    document: {
      getElementById: (id) => (elements[id] || (elements[id] = makeEl())),
      createElement: () => makeEl(),
    },
    window: { devicePixelRatio: 1 },
    localStorage: { getItem: () => null, setItem: () => {} },
    confirm: () => true,
    addEventListener: () => {},
    Peer: makePeerClass(bus, role),
  };
  vm.createContext(sandbox);
  return { sandbox, elements };
}

const code = ["boards.js", "engine.js", "game.js"]
  .map((f) => fs.readFileSync(__dirname + "/../" + f, "utf8"))
  .join("\n");
const EXPORT = `
;globalThis.__t = {
  get game() { return game; },
  get mode() { return mode; },
  get scoringLocked() { return scoringLocked; },
  get netState() { return netState; },
  get myRoomCode() { return myRoomCode; },
  get netText() { return netStatusEl.textContent; },
  get captures() { return game.captured; },
  get navPos() { return navPos; },
  get deadSet() { return deadSet; },
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

const flush = (n = 6) => new Promise((res) => {
  let left = n;
  (function tick() { if (--left <= 0) return res(); setImmediate(tick); })();
});

let passed = 0, failed = 0;
function ok(name, cond, detail) {
  if (cond) { passed++; console.log("  ✓ " + name); }
  else { failed++; console.error("  ✗ " + name + (detail ? "  [" + detail + "]" : "")); }
}

async function main() {
  console.log("═ 联机同步测试（先下棋 → 后联机） ═");
  const bus = new NetBus();
  const host = buildSandbox(bus, "host");
  const guest = buildSandbox(bus, "guest");
  const H = loadApp(host);
  const G = loadApp(guest);

  // 1. 房主先本地下了 3 手（黑(3,3) 白(3,4) 黑(4,3)）
  clickAt(host.elements, 3, 3);
  clickAt(host.elements, 3, 4);
  clickAt(host.elements, 4, 3);
  ok("房主本地已下 3 手", H.game.moves.length === 3, "moves=" + H.game.moves.length);
  ok("房主第 1 手为黑(3,3)", H.game.board[3][3] === 1);

  // 2. 房主创建房间
  host.elements["btn-create-room"]._h.click();
  await flush();
  ok("房主创建房间成功", H.netState === "host" && H.myRoomCode.length === 4, "code=" + H.myRoomCode);
  const roomCode = H.myRoomCode;

  // 3. 等待时房主还能继续下（连接未建立 → 自由落子）
  clickAt(host.elements, 4, 4);
  ok("等待时房主继续落子", H.game.moves.length === 4 && H.game.board[4][4] === 2);

  // 4. 对方加入房间
  guest.elements["room-input"].value = roomCode;
  guest.elements["btn-do-join"]._h.click();
  await flush(12);
  ok("对方加入成功", G.netState === "guest");

  // 5. ★ 关键：对方应看到房主先下的全部棋子 ★
  ok("对方同步看到黑(3,3)", G.game.board[3][3] === 1);
  ok("对方同步看到白(3,4)", G.game.board[3][4] === 2);
  ok("对方同步看到黑(4,3)", G.game.board[4][3] === 1);
  ok("对方同步看到白(4,4)", G.game.board[4][4] === 2);
  ok("对方手数一致", G.game.moves.length === 4, "moves=" + G.game.moves.length);
  ok("轮到黑方（房主执黑）", G.game.current === 1, "current=" + G.game.current);
  ok("双方局面完全一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

  // 6. 房主落子 → 对方同步
  clickAt(host.elements, 5, 5);
  await flush();
  ok("房主落子后对方同步（黑(5,5)）", G.game.board[5][5] === 1 && G.game.moves.length === 5);
  ok("双方仍一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

  // 7. 对方落子 → 房主同步
  clickAt(guest.elements, 5, 4);
  await flush();
  ok("对方落子后房主同步（白(5,4)）", H.game.board[5][4] === 2 && H.game.moves.length === 6);
  ok("双方仍一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

  // 8. 虚手同步
  host.elements["btn-pass"]._h.click();  // 黑虚手（轮到黑）
  await flush();
  ok("虚手同步：对方手数 +1", G.game.moves.length === 7 && G.game.passCount === 1);
  ok("双方仍一致", JSON.stringify(H.game.board) === JSON.stringify(G.game.board));

  // 9. 终局 → 计分状态同步
  guest.elements["btn-pass"]._h.click();  // 白虚手（双虚终局）
  await flush();
  ok("双虚后双方进入计分", H.mode === "scoring" && G.mode === "scoring");
  // 房主确认终局 → 对方锁定
  host.elements["btn-confirm"]._h.click();
  await flush();
  ok("房主确认后对方同步锁定", G.scoringLocked === true);

  console.log("");
  console.log("═ 场景 2：对方加入时房主已在计分阶段 ═");
  const bus2 = new NetBus();
  const h2 = buildSandbox(bus2, "host");
  const g2 = buildSandbox(bus2, "guest");
  const H2 = loadApp(h2);
  const G2 = loadApp(g2);
  // 房主下 2 手后直接终局（进入计分）
  clickAt(h2.elements, 3, 3);
  clickAt(h2.elements, 3, 4);
  h2.elements["btn-end"]._h.click();
  ok("房主进入计分阶段", H2.mode === "scoring");
  // 对方此时才加入
  h2.elements["btn-create-room"]._h.click();
  await flush();
  g2.elements["room-input"].value = H2.myRoomCode;
  g2.elements["btn-do-join"]._h.click();
  await flush(12);
  ok("对方加入成功", G2.netState === "guest");
  ok("对方同步为计分阶段", G2.mode === "scoring");
  ok("对方同步看到 2 手棋子", G2.game.moves.length === 2 && G2.game.board[3][3] === 1 && G2.game.board[3][4] === 2);
  ok("双方局面一致", JSON.stringify(H2.game.board) === JSON.stringify(G2.game.board));
  // 房主标记死子（点击 (3,3)）→ 双方 deadSet 同步
  clickAt(h2.elements, 3, 3);
  await flush();
  ok("房主标记后自己 deadSet 更新", H2.deadSet.has("3,3"));
  ok("对方 deadSet 同步", G2.deadSet.has("3,3"));
  ok("双方 deadSet 完全一致", JSON.stringify([...H2.deadSet].sort()) === JSON.stringify([...G2.deadSet].sort()));

  console.log("");
  console.log("═ 场景 3：每步棋全量同步——状态被破坏也能自愈 ═");
  const bus3 = new NetBus();
  const h3 = buildSandbox(bus3, "host");
  const g3 = buildSandbox(bus3, "guest");
  const H3 = loadApp(h3);
  const G3 = loadApp(g3);
  // 本地下 2 手 → 建房 → 对方加入
  clickAt(h3.elements, 3, 3);
  clickAt(h3.elements, 3, 4);
  h3.elements["btn-create-room"]._h.click();
  await flush();
  g3.elements["room-input"].value = H3.myRoomCode;
  g3.elements["btn-do-join"]._h.click();
  await flush(12);
  ok("连接后双方一致", JSON.stringify(H3.game.board) === JSON.stringify(G3.game.board));
  // 人为破坏对方状态：删棋子 + 截断历史
  G3.game.board[3][3] = 0;
  G3.game.board[3][4] = 0;
  G3.game.moves.length = 0;
  ok("已人为破坏对方状态", G3.game.moves.length === 0 && G3.game.board[3][3] === 0);
  // 房主下一步棋（携带完整局面数据包）→ 对方应自愈
  clickAt(h3.elements, 4, 3);
  await flush();
  ok("对方自愈：棋子全部恢复且手数一致",
    G3.game.moves.length === 3 &&
    G3.game.board[3][3] === 1 &&
    G3.game.board[3][4] === 2 &&
    G3.game.board[4][3] === 1);
  ok("自愈后双方完全一致", JSON.stringify(H3.game.board) === JSON.stringify(G3.game.board));

  console.log("");
  console.log("═ 场景 4：网络检测按钮 ═");
  const bus4 = new NetBus();
  const h4 = buildSandbox(bus4, "host");
  const H4 = loadApp(h4);
  h4.elements["btn-net-check"]._h.click();
  await flush(8);
  ok("检测显示信令连接成功", H4.netText.indexOf("信令连接成功") >= 0, "text=" + H4.netText);

  console.log("");
  console.log("═ 场景 5：房间号无效/房主不在线 → 友好错误 ═");
  const bus5 = new NetBus();
  const g5 = buildSandbox(bus5, "guest");
  const G5 = loadApp(g5);
  g5.elements["room-input"].value = "ZZZZ";
  g5.elements["btn-do-join"]._h.click();
  await flush(8);
  ok("无效房间号给出友好错误", G5.netText.indexOf("找不到该房间") >= 0, "text=" + G5.netText);

  console.log("\n" + (failed ? "✗ 存在失败" : "✓ 联机同步测试通过") + "（" + passed + " 通过，失败 " + failed + "）");
  process.exitCode = failed ? 1 : 0;
}

main();
