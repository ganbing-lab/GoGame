/* ============================================================
 * game.js — 围棋网页版 UI 与交互
 *   · 本地双人对弈（同屏轮流）
 *   · 联机对战（WebRTC 点对点，PeerJS，纯静态可托管于 GitHub Pages）
 *   · 异形棋盘（内置预设 / 导入 JSON）
 *   · 终局计分：自动死子检测 + 手动标记，数目法 / 数子法双显示
 * ============================================================ */
"use strict";

/* ───────── 常量 ───────── */
const APP_VERSION = "v1.3.0";

// 棋盘布局尺寸（随屏幕宽度自适应，手机端缩小格子）
let CELL = 36;
let MARGIN = 44;

function calcLayout() {
  const w = (typeof window !== "undefined" && window.innerWidth) || 800;
  if (w < 520) { CELL = 24; MARGIN = 30; }
  else if (w < 760) { CELL = 30; MARGIN = 36; }
  else { CELL = 36; MARGIN = 44; }
}

/* ───────── 全局状态 ───────── */
let game = null;            // GoGame 实例
let boardConfig = null;     // {name, size, disabled}
let navPos = 0;             // 翻棋位置（0..moves.length）
let mode = "playing";       // playing | scoring
let scoringLocked = false;  // 计分已确认
let deadSet = new Set();    // 死子坐标 "r,c"
let regionOwner = new Map();// 空区域手动归属：区域代表点 -> BLACK|WHITE
let hoverPos = null;
let hintTimer = null;

// 联机
let netState = "local";     // local | host | guest
let netMyColor = null;      // 联机时自己的颜色
let peer = null;            // Peer 实例
let netConn = null;         // DataConnection
let myRoomCode = "";

/* ───────── DOM ───────── */
const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const boardSel = document.getElementById("board-select");
const turnEl = document.getElementById("turn");
const moveNumEl = document.getElementById("move-num");
const capturesEl = document.getElementById("captures");
const hintEl = document.getElementById("hint");
const btnPass = document.getElementById("btn-pass");
const btnEnd = document.getElementById("btn-end");
const btnResign = document.getElementById("btn-resign");
const btnUndo = document.getElementById("btn-undo");
const btnPrev = document.getElementById("btn-prev");
const btnNext = document.getElementById("btn-next");
const btnNew = document.getElementById("btn-new");
const scoringCard = document.getElementById("scoring-card");
const scoresEl = document.getElementById("scores");
const btnAutodead = document.getElementById("btn-autodead");
const btnConfirm = document.getElementById("btn-confirm");
const btnResume = document.getElementById("btn-resume");
const btnCreateRoom = document.getElementById("btn-create-room");
const btnJoinRoom = document.getElementById("btn-join-room");
const btnDoJoin = document.getElementById("btn-do-join");
const joinBox = document.getElementById("join-box");
const roomInput = document.getElementById("room-input");
const roomInfo = document.getElementById("room-info");
const netStatusEl = document.getElementById("net-status");
const btnLeaveNet = document.getElementById("btn-leave-net");
const btnNetCheck = document.getElementById("btn-net-check");
const btnImport = document.getElementById("btn-import");
const boardFile = document.getElementById("board-file");
const boardNameEl = document.getElementById("board-name");
const versionEl = document.getElementById("version-tag");

/* ═══════════════════════ 棋盘尺寸与坐标 ═══════════════════════ */
function boardPx() {
  return MARGIN * 2 + CELL * (game.size - 1);
}

function setupCanvas() {
  calcLayout();
  const px = boardPx(), dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(px * dpr);
  canvas.height = Math.round(px * dpr);
  canvas.style.width = px + "px";
  canvas.style.height = px + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function toPx(r, c) {
  return [MARGIN + c * CELL, MARGIN + r * CELL];
}

function toGrid(px, py) {
  const c = Math.round((px - MARGIN) / CELL);
  const r = Math.round((py - MARGIN) / CELL);
  if (r < 0 || r >= game.size || c < 0 || c >= game.size) return null;
  if (game.disabled.has(gkey(r, c))) return null;
  return [r, c];
}

function starPoints() {
  const n = game.size;
  let pts;
  if (n === 19) {
    pts = [[3, 3], [3, 9], [3, 15], [9, 3], [9, 9], [9, 15], [15, 3], [15, 9], [15, 15]];
  } else if (n === 13) {
    pts = [[3, 3], [3, 9], [9, 3], [9, 9], [6, 6]];
  } else if (n === 9) {
    pts = [[2, 2], [2, 6], [6, 2], [6, 6], [4, 4]];
  } else {
    const s19 = [[3, 3], [3, 9], [3, 15], [9, 3], [9, 9], [9, 15], [15, 3], [15, 9], [15, 15]];
    pts = s19.map(([r, c]) => [Math.round(r * (n - 1) / 18), Math.round(c * (n - 1) / 18)]);
  }
  return pts.filter(([r, c]) => !game.disabled.has(gkey(r, c)));
}

function colLabels() {
  const out = [];
  for (let i = 0; i < game.size; i++) {
    out.push(String.fromCharCode(65 + i + (i >= 8 ? 1 : 0)));
  }
  return out;
}

/* ═══════════════════════ 绘制 ═══════════════════════ */
function drawLineSegments(x1, y1, x2, y2, isRow, idx) {
  const dl = [];
  for (const k of game.disabled) {
    const [r, c] = k.split(",").map(Number);
    if (isRow && r === idx) dl.push(c);
    if (!isRow && c === idx) dl.push(r);
  }
  dl.sort((a, b) => a - b);
  ctx.beginPath();
  if (!dl.length) {
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    return;
  }
  let s = isRow ? x1 : y1;
  const e = isRow ? x2 : y2;
  for (const p of dl) {
    const cp = MARGIN + p * CELL;
    const gs = cp - CELL / 2;
    if (s < gs) {
      ctx.moveTo(isRow ? s : x1, isRow ? y1 : s);
      ctx.lineTo(isRow ? gs : x2, isRow ? y2 : gs);
    }
    s = cp + CELL / 2;
  }
  if (s < e) {
    ctx.moveTo(isRow ? s : x1, isRow ? y1 : s);
    ctx.lineTo(isRow ? e : x2, isRow ? y2 : e);
  }
  ctx.stroke();
}

function drawBoard() {
  const px = boardPx();
  ctx.clearRect(0, 0, px, px);
  // 木色底 + 渐变
  const g = ctx.createLinearGradient(0, 0, px, px);
  g.addColorStop(0, "#EACB9B");
  g.addColorStop(1, "#D4A96B");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, px, px);
  // 木纹（确定性，避免每帧闪烁）
  ctx.strokeStyle = "rgba(150, 110, 55, 0.15)";
  ctx.lineWidth = 1;
  for (let i = 0; i < 30; i++) {
    const y = ((i * 41) % px) + 6;
    const x0 = ((i * 67) % px) - 100;
    ctx.beginPath();
    ctx.moveTo(x0, y);
    ctx.quadraticCurveTo(x0 + 110, y + 10, x0 + 240, y - 5);
    ctx.stroke();
  }
  // 网格线（禁用格处断开）
  ctx.strokeStyle = "#4A3728";
  ctx.lineWidth = 1;
  for (let i = 0; i < game.size; i++) {
    drawLineSegments(MARGIN, MARGIN + i * CELL, MARGIN + CELL * (game.size - 1), MARGIN + i * CELL, true, i);
    drawLineSegments(MARGIN + i * CELL, MARGIN, MARGIN + i * CELL, MARGIN + CELL * (game.size - 1), false, i);
  }
  // 禁用格
  const side = CELL / 2;
  for (const k of game.disabled) {
    const [r, c] = k.split(",").map(Number);
    const [x, y] = toPx(r, c);
    ctx.fillStyle = "#EACB9B";
    ctx.fillRect(x - side - 1, y - side - 1, side * 2 + 2, side * 2 + 2);
    ctx.fillStyle = "#8B7355";
    ctx.fillRect(x - side + 2, y - side + 2, side * 2 - 4, side * 2 - 4);
  }
  // 星位
  ctx.fillStyle = "#4A3728";
  for (const [r, c] of starPoints()) {
    const [x, y] = toPx(r, c);
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  }
  // 坐标
  const labels = colLabels();
  ctx.font = "10px Arial";
  ctx.fillStyle = "#4A3728";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let i = 0; i < game.size; i++) {
    const x = MARGIN + i * CELL;
    const y = MARGIN + i * CELL;
    ctx.fillText(labels[i], x, 13);
    ctx.fillText(labels[i], x, px - 13);
    ctx.fillText(String(game.size - i), 13, y);
    ctx.fillText(String(game.size - i), px - 13, y);
  }
}

function drawStone(r, c, color, ghost) {
  const [x, y] = toPx(r, c);
  const rad = CELL * 0.44 - 1;
  const g = ctx.createRadialGradient(x - rad * 0.35, y - rad * 0.35, rad * 0.15, x, y, rad);
  if (color === COLOR_BLACK) {
    g.addColorStop(0, ghost ? "#8f8f8f" : "#5a5a5a");
    g.addColorStop(1, ghost ? "#6a6a6a" : "#0c0c0c");
  } else {
    g.addColorStop(0, ghost ? "#ffffff" : "#fdfdfd");
    g.addColorStop(1, ghost ? "#d9d9d9" : "#cfcfcf");
  }
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, rad, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = color === COLOR_BLACK ? "#000000" : "#b2b2b2";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(x, y, rad, 0, Math.PI * 2);
  ctx.stroke();
  // 高光
  ctx.fillStyle = "rgba(255,255,255," + (ghost ? "0.15" : "0.28") + ")";
  ctx.beginPath();
  ctx.arc(x - rad * 0.35, y - rad * 0.35, rad * 0.35, 0, Math.PI * 2);
  ctx.fill();
}

function drawDeadMark(r, c) {
  const [x, y] = toPx(r, c);
  const s = CELL * 0.3;
  ctx.strokeStyle = "#E23B3B";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(x - s, y - s);
  ctx.lineTo(x + s, y + s);
  ctx.moveTo(x + s, y - s);
  ctx.lineTo(x - s, y + s);
  ctx.stroke();
}

/* 空区域计算：返回 [{cells, rep, owner}]，owner 为 BLACK/WHITE/null */
function computeRegions() {
  const regions = [];
  const visited = new Set();
  for (let r = 0; r < game.size; r++) {
    for (let c = 0; c < game.size; c++) {
      const k = gkey(r, c);
      const cell = game.board[r][c];
      const open = cell === COLOR_EMPTY || deadSet.has(k);
      if (!open || visited.has(k)) continue;
      const cells = game.emptyRegionAt(r, c, deadSet);
      for (const [rr, cc] of cells) visited.add(gkey(rr, cc));
      const rep = cells.map(([rr, cc]) => gkey(rr, cc)).sort()[0];
      let owner = regionOwner.get(rep) || null;
      if (!owner) {
        const borders = new Set();
        for (const [rr, cc] of cells) {
          for (const [nr, nc] of game.neighbors(rr, cc)) {
            const cc2 = game.board[nr][nc];
            if (cc2 !== COLOR_EMPTY && !deadSet.has(gkey(nr, nc))) borders.add(cc2);
          }
        }
        if (borders.size === 1) owner = [...borders][0];
      }
      regions.push({ cells, rep, owner });
    }
  }
  return regions;
}

function drawRegionTints() {
  if (mode !== "scoring") return;
  for (const reg of computeRegions()) {
    if (!reg.owner) continue;
    ctx.fillStyle = reg.owner === COLOR_BLACK ? "rgba(0,0,0,0.13)" : "rgba(255,255,255,0.42)";
    const s = CELL / 2 - 1;
    for (const [rr, cc] of reg.cells) {
      const [x, y] = toPx(rr, cc);
      ctx.fillRect(x - s, y - s, s * 2, s * 2);
    }
  }
}

function render() {
  drawBoard();
  drawRegionTints();
  const bd = game.board;
  for (let r = 0; r < game.size; r++) {
    for (let c = 0; c < game.size; c++) {
      const cell = bd[r][c];
      if (cell !== COLOR_EMPTY) {
        drawStone(r, c, cell, false);
        if (deadSet.has(gkey(r, c))) drawDeadMark(r, c);
      }
    }
  }
  // 最后一手高亮
  if (mode === "playing" && navPos > 0 && navPos <= game.moves.length) {
    const last = game.moves[navPos - 1];
    if (last.r >= 0) {
      const [x, y] = toPx(last.r, last.c);
      ctx.fillStyle = "#E23B3B";
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  // 悬停预览
  if (hoverPos && mode === "playing" && !game.gameOver && canActNow()) {
    const [hr, hc] = hoverPos;
    if (game.board[hr][hc] === COLOR_EMPTY) drawStone(hr, hc, game.current, true);
  }
}

/* ═══════════════════════ 对局操作 ═══════════════════════ */
function netConnected() {
  return netState !== "local" && !!netConn && netConn.open;
}

function canActNow() {
  if (mode !== "playing" || game.gameOver) return false;
  if (netState !== "local") {
    // 连接未建立（如房主等待对方加入）→ 可自由落子，连接后一次性全量同步
    if (!netConnected()) return true;
    return game.current === netMyColor;
  }
  return true;
}

function flashHint(text) {
  hintEl.textContent = text;
  clearTimeout(hintTimer);
  if (text) hintTimer = setTimeout(() => { hintEl.textContent = ""; }, 2500);
}

function newGameWith(config) {
  boardConfig = config;
  game = new GoGame(config);
  navPos = 0;
  mode = "playing";
  scoringLocked = false;
  deadSet = new Set();
  regionOwner = new Map();
  boardNameEl.textContent = config.name + (config.disabled.length ? "（异形）" : "");
  setupCanvas();
  render();
  updatePanel();
}

function jumpTo(n) {
  if (mode !== "playing") return;
  navPos = game.replayTo(n);
  render();
  updatePanel();
}

function tryPlay(r, c) {
  if (!canActNow()) {
    if (netConnected()) flashHint("等待对方落子…");
    return;
  }
  if (navPos < game.moves.length) jumpTo(game.moves.length);
  const taken = game.play(r, c);
  if (taken === -1) { flashHint("此处不能落子"); return; }
  navPos = game.moves.length;
  netSend({ type: "move", s: buildSync() });   // 每步棋携带完整局面
  render();
  updatePanel();
  if (taken > 0) flashHint("提 " + taken + " 子");
}

function doPass() {
  if (!canActNow()) return;
  if (navPos < game.moves.length) jumpTo(game.moves.length);
  const ended = game.passMove();
  navPos = game.moves.length;
  if (ended) {
    enterScoring();
  } else {
    render();
    updatePanel();
  }
  netSend({ type: "pass", s: buildSync() });
}

function doEndGame() {
  if (mode !== "playing" || game.gameOver) return;
  if (!confirm("确定终局吗？将进入标记计分阶段。")) return;
  game.gameOver = true;
  enterScoring();
  netSend({ type: "endGame", s: buildSync() });
}

function doResign() {
  if (mode !== "playing" || game.gameOver) return;
  const name = game.current === COLOR_BLACK ? "黑方" : "白方";
  if (!confirm(name + "确定认输吗？")) return;
  game.resign();
  netSend({ type: "resign", s: buildSync() });
  render();
  updatePanel();
}

function doUndo() {
  if (netConnected()) { flashHint("联机对局不支持悔棋"); return; }
  if (mode !== "playing" || game.gameOver) return;
  if (navPos < game.moves.length) jumpTo(game.moves.length);
  if (!game.moves.length) return;
  game.moves.pop();
  jumpTo(game.moves.length);
}

function doNewGame() {
  if (netState !== "local") {
    if (!confirm("确定重新开始本局吗？对方也会收到重开通知。")) return;
    newGameWith(boardConfig);
    netSend({ type: "rematch", s: buildSync() });
    return;
  }
  newGameWith(boardConfig);
}

/* ═══════════════════════ 终局计分 ═══════════════════════ */
function enterScoring() {
  mode = "scoring";
  scoringLocked = false;
  deadSet = new Set(game.autoDetectDead());
  regionOwner = new Map();
  render();
  updatePanel();
}

function autoDetectAgain() {
  if (mode !== "scoring" || scoringLocked) return;
  deadSet = new Set(game.autoDetectDead());
  regionOwner = new Map();
  netSend({ type: "autodead", s: buildSync() });
  render();
  updatePanel();
}

/** 整串切换死/活：点击 (r,c) 所在同色连通棋串，整串一起标记或取消 */
function toggleDeadGroup(r, c) {
  if (!game.inBounds(r, c) || game.board[r][c] === COLOR_EMPTY) return;
  const grp = game.group(r, c);
  const keys = grp.map(([rr, cc]) => gkey(rr, cc));
  const allDead = keys.every((kk) => deadSet.has(kk));
  if (allDead) {
    for (const kk of keys) deadSet.delete(kk);
  } else {
    for (const kk of keys) deadSet.add(kk);
  }
}

function handleScoringClick(r, c) {
  if (mode !== "scoring" || scoringLocked) return;
  const cell = game.board[r][c];
  if (cell !== COLOR_EMPTY) {
    // 点击棋子：自动选中整个连通棋串一起切换死/活
    toggleDeadGroup(r, c);
  } else {
    // 轮换空区域归属：自动 → 黑 → 白 → 自动
    const cells = game.emptyRegionAt(r, c, deadSet);
    if (!cells.length) return;
    const rep = cells.map(([rr, cc]) => gkey(rr, cc)).sort()[0];
    const cur = regionOwner.get(rep) || null;
    const next = cur === null ? COLOR_BLACK : cur === COLOR_BLACK ? COLOR_WHITE : null;
    if (next === null) regionOwner.delete(rep);
    else regionOwner.set(rep, next);
  }
  netSend({ type: "mark", s: buildSync() });   // 标记结果随完整局面同步
  render();
  updatePanel();
}

function computeScores() {
  let terrB = 0, terrW = 0, liveB = 0, liveW = 0;
  for (const reg of computeRegions()) {
    if (reg.owner === COLOR_BLACK) terrB += reg.cells.length;
    else if (reg.owner === COLOR_WHITE) terrW += reg.cells.length;
  }
  for (let r = 0; r < game.size; r++) {
    for (let c = 0; c < game.size; c++) {
      const cell = game.board[r][c];
      if (cell !== COLOR_EMPTY && !deadSet.has(gkey(r, c))) {
        if (cell === COLOR_BLACK) liveB++; else liveW++;
      }
    }
  }
  return {
    terrB, terrW, liveB, liveW,
    jpB: terrB + game.captured[COLOR_BLACK],
    jpW: terrW + game.captured[COLOR_WHITE] + KOMI,
    cnB: liveB + terrB,
    cnW: liveW + terrW + KOMI / 2,
  };
}

function resumeFromScoring() {
  mode = "playing";
  scoringLocked = false;
  game.gameOver = false;
  deadSet = new Set();
  regionOwner = new Map();
  render();
  updatePanel();
}

/* ═══════════════════════ 联机（PeerJS / WebRTC） ═══════════════════════ */
function peerAvailable() {
  return typeof Peer !== "undefined";
}

function netSend(msg) {
  if (netConn && netConn.open) {
    try { netConn.send(msg); } catch (e) { /* ignore */ }
  }
}

/** 构建完整局面数据包：棋盘 + 全部落子历史 + 计分/终局状态 */
function buildSync() {
  return {
    board: { name: boardConfig.name, size: boardConfig.size, disabled: [...boardConfig.disabled] },
    moves: game.moves.map((m) => ({ r: m.r, c: m.c, color: m.color })),
    mode: mode,
    dead: [...deadSet],
    regionOwner: [...regionOwner.entries()],
    scoringLocked: scoringLocked,
    gameOver: game.gameOver,
    winner: game.winner,
    captured: { [COLOR_BLACK]: game.captured[COLOR_BLACK], [COLOR_WHITE]: game.captured[COLOR_WHITE] },
    passCount: game.passCount,
  };
}

/** 全量应用对方发来的局面数据包（直接恢复为发送方状态） */
function applySync(s) {
  if (!s || !s.board) return;
  applyBoardConfig(s.board, true);
  if (Array.isArray(s.moves) && s.moves.length) {
    game.moves = s.moves.map((m) => ({ r: m.r, c: m.c, color: m.color }));
    game.replayTo(game.moves.length);
    navPos = game.moves.length;
  }
  game.gameOver = !!s.gameOver;
  game.winner = s.winner || null;
  game.passCount = s.passCount || 0;
  if (s.captured) {
    game.captured[COLOR_BLACK] = s.captured[COLOR_BLACK] || 0;
    game.captured[COLOR_WHITE] = s.captured[COLOR_WHITE] || 0;
  }
  mode = s.mode === "scoring" ? "scoring" : "playing";
  scoringLocked = !!s.scoringLocked;
  deadSet = new Set(s.dead || []);
  regionOwner = new Map(s.regionOwner || []);
  render();
  updatePanel();
}

function netStatus(text) {
  netStatusEl.textContent = text;
}

// ── 网络检测：PeerJS 库 + WebRTC 支持 + 信令服务器连通性 ──
let netCheckPeer = null;
function destroyCheckPeer() {
  if (netCheckPeer) {
    try { netCheckPeer.destroy(); } catch (e) { /* ignore */ }
    netCheckPeer = null;
  }
}

function checkNetwork() {
  destroyCheckPeer();
  if (!peerAvailable()) {
    netStatus("✗ PeerJS 库未加载（需联网从 CDN 加载）");
    return;
  }
  const w = typeof window !== "undefined" ? window : {};
  const rtcOK = !!(w.RTCPeerConnection || w.webkitRTCPeerConnection);
  netStatus("正在检测网络…");
  const t0 = Date.now();
  try {
    netCheckPeer = new Peer();
  } catch (e) {
    netStatus("✗ 无法创建连接：" + e.message);
    return;
  }
  netCheckPeer.on("open", () => {
    const ms = Date.now() - t0;
    netStatus(
      "✓ 网络正常：信令连接成功（" + ms + "ms）" +
      (rtcOK ? " · WebRTC 可用" : " · WebRTC 不可用")
    );
    destroyCheckPeer();
  });
  netCheckPeer.on("error", (e) => {
    netStatus("✗ 信令服务器连接失败：" + (e.type || e.message || "未知错误"));
    destroyCheckPeer();
  });
  // 兜底超时
  setTimeout(destroyCheckPeer, 10000);
}

function makeRoomCode() {
  return Math.random().toString(36).slice(2, 6).toUpperCase();
}

function createRoom() {
  if (!peerAvailable()) {
    flashHint("无法加载 PeerJS（需联网从 CDN 加载，本地双人不受影响）");
    return;
  }
  destroyCheckPeer();
  if (netState !== "local") leaveNet();
  const code = makeRoomCode();
  const id = "gogame-" + code;
  netState = "host";
  myRoomCode = code;
  try {
    peer = new Peer(id);
  } catch (e) {
    flashHint("创建失败：" + e.message);
    netState = "local";
    return;
  }
  peer.on("open", () => {
    netStatus("房间已创建，房间号：" + code + "，等待对方加入…");
  });
  peer.on("connection", (conn) => {
    netConn = conn;
    conn.on("open", onNetConnected);
    conn.on("data", handleNetMsg);
    conn.on("close", onNetClosed);
    conn.on("error", (e) => console.error("conn error:", e));
  });
  peer.on("error", (e) => {
    console.error("peer error:", e);
    if (e.type === "unavailable-id") {
      netStatus("房间号冲突，请重新创建");
      leaveNet();
    } else {
      netStatus("连接错误：" + e.type);
    }
  });
  updatePanel();
}

function joinRoom(code) {
  if (!peerAvailable()) {
    flashHint("无法加载 PeerJS（需联网从 CDN 加载，本地双人不受影响）");
    return;
  }
  destroyCheckPeer();
  if (netState !== "local") leaveNet();
  code = (code || "").trim().toUpperCase();
  if (!/^[A-Z0-9]{4}$/.test(code)) { flashHint("房间号格式：4 位字母数字"); return; }
  netState = "guest";
  try {
    peer = new Peer();
  } catch (e) {
    flashHint("连接失败：" + e.message);
    netState = "local";
    return;
  }
  peer.on("open", () => {
    const conn = peer.connect("gogame-" + code, { reliable: true });
    netConn = conn;
    conn.on("open", onNetConnected);
    conn.on("data", handleNetMsg);
    conn.on("close", onNetClosed);
    conn.on("error", (e) => console.error("conn error:", e));
    netStatus("正在加入房间 " + code + " …");
  });
  peer.on("error", (e) => {
    console.error("peer error:", e);
    netStatus("连接错误：" + e.type);
  });
  updatePanel();
}

function onNetConnected() {
  if (netState === "host") {
    netMyColor = COLOR_BLACK;
    netStatus("已连接！对方为白方，你执黑先行。");
    // 发送完整局面数据包（棋盘 + 全部落子历史 + 计分状态）
    netConn.send({ type: "hello", s: buildSync() });
  } else {
    netMyColor = COLOR_WHITE;
    netStatus("已连接，等待房主发送棋盘…");
  }
  updatePanel();
}

function handleNetMsg(msg) {
  if (!msg || typeof msg !== "object") return;
  // 任何消息都携带完整局面数据包，收到后直接全量恢复为发送方状态
  if (msg.s) applySync(msg.s);
  if (msg.type === "hello" && netState === "guest") {
    netStatus("已加入房间！对方执黑，你执白。");
  }
}

function cleanupPeer() {
  if (netConn) { try { netConn.close(); } catch (e) { /* ignore */ } }
  netConn = null;
  if (peer) { try { peer.destroy(); } catch (e) { /* ignore */ } }
  peer = null;
}

function leaveNet() {
  cleanupPeer();
  netState = "local";
  netMyColor = null;
  myRoomCode = "";
  netStatus("");
  updatePanel();
}

function onNetClosed() {
  if (netState === "local") return;
  flashHint("对方已断开连接");
  cleanupPeer();
  netState = "local";
  netMyColor = null;
  updatePanel();
}

/* ═══════════════════════ 面板 UI ═══════════════════════ */
function updatePanel() {
  // 轮次 / 状态
  if (mode === "scoring") {
    turnEl.textContent = scoringLocked ? "计分已确认" : "标记阶段 — 点击棋盘调整";
  } else if (game.gameOver) {
    if (game.winner) {
      turnEl.textContent = (game.winner === COLOR_BLACK ? "⚫ 黑方" : "⚪ 白方") + "胜（认输）";
    } else {
      turnEl.textContent = "对局结束";
    }
  } else {
    const who = game.current === COLOR_BLACK ? "⚫ 黑方" : "⚪ 白方";
    if (netConnected()) {
      turnEl.textContent = who + (game.current === netMyColor ? "（你）" : "（对方）");
    } else if (netState !== "local") {
      turnEl.textContent = who + "（等待对方加入…）";
    } else {
      turnEl.textContent = who + " 落子";
    }
  }
  moveNumEl.textContent = "第 " + navPos + " / " + game.moves.length + " 手";
  capturesEl.textContent = "提子 ⚫" + game.captured[COLOR_BLACK] + " ⚪" + game.captured[COLOR_WHITE];

  // 对局按钮
  const inPlay = mode === "playing" && !game.gameOver;
  const netLive = netConnected();
  btnPass.disabled = !inPlay || (netLive && game.current !== netMyColor);
  btnEnd.disabled = !inPlay;
  btnResign.disabled = !inPlay;
  btnUndo.disabled = !inPlay || netLive;
  btnPrev.disabled = mode !== "playing" || navPos <= 0 || netLive;
  btnNext.disabled = mode !== "playing" || navPos >= game.moves.length || netLive;
  boardSel.disabled = netState !== "local";
  btnImport.disabled = netState !== "local";

  // 计分区
  if (mode === "scoring") {
    scoringCard.classList.remove("hidden");
    const s = computeScores();
    const jpDiff = s.jpB - s.jpW;
    const cnDiff = s.cnB - s.cnW;
    const jpWin = jpDiff > 0 ? "黑胜 " + jpDiff.toFixed(1) + " 目" : jpDiff < 0 ? "白胜 " + (-jpDiff).toFixed(1) + " 目" : "平局";
    const cnWin = cnDiff > 0 ? "黑胜 " + cnDiff.toFixed(1) + " 子" : cnDiff < 0 ? "白胜 " + (-cnDiff).toFixed(1) + " 子" : "平局";
    scoresEl.innerHTML =
      '<div class="score-line"><span class="score-rule">数目法（日本）</span><span>⚫ ' + s.jpB.toFixed(1) +
      ' · ⚪ ' + s.jpW.toFixed(1) + '</span><span class="score-result">' + jpWin + '</span></div>' +
      '<div class="score-line"><span class="score-rule">数子法（中国）</span><span>⚫ ' + s.cnB.toFixed(1) +
      ' · ⚪ ' + s.cnW.toFixed(1) + '</span><span class="score-result">' + cnWin + '</span></div>' +
      '<div class="score-detail">领地 ⚫' + s.terrB + ' ⚪' + s.terrW + ' · 活子 ⚫' + s.liveB + ' ⚪' + s.liveW +
      ' · 提子 ⚫' + game.captured[COLOR_BLACK] + ' ⚪' + game.captured[COLOR_WHITE] + '</div>';
    btnConfirm.disabled = scoringLocked;
    btnConfirm.textContent = scoringLocked ? "已确认 ✓" : "确认终局";
  } else {
    scoringCard.classList.add("hidden");
  }

  // 联机卡
  if (netState === "local") {
    joinBox.classList.add("hidden");
    roomInfo.classList.add("hidden");
    btnCreateRoom.disabled = false;
    btnJoinRoom.disabled = false;
    btnLeaveNet.classList.add("hidden");
  } else {
    btnCreateRoom.disabled = true;
    btnJoinRoom.disabled = true;
    btnLeaveNet.classList.remove("hidden");
    if (netState === "host") {
      roomInfo.classList.remove("hidden");
      roomInfo.innerHTML = "房间号：<b>" + myRoomCode + "</b> · 你执黑";
    } else {
      roomInfo.classList.remove("hidden");
      roomInfo.innerHTML = "你执白";
    }
  }
}

/* ═══════════════════════ 棋盘选择 / 导入 ═══════════════════════ */
function applyBoardConfig(config, fromNet) {
  newGameWith(config);
  // 同步下拉框
  const idx = BOARD_PRESETS.findIndex(
    (p) => p.name === config.name && p.size === config.size
  );
  if (idx >= 0) {
    boardSel.value = String(idx);
  } else {
    boardSel.value = "custom";
  }
  if (!fromNet) {
    try { localStorage.setItem("gogame-board", boardSel.value); } catch (e) { /* ignore */ }
  }
}

function normalizeBoard(data) {
  const size = parseInt(data.size, 10);
  if (!(size >= 2 && size <= 25)) throw new Error("size 必须是 2~25 的整数");
  const disabled = Array.isArray(data.disabled)
    ? data.disabled.filter((p) => Array.isArray(p) && p.length >= 2)
    : [];
  return { name: String(data.name || "自定义棋盘"), size, disabled };
}

/* ═══════════════════════ 事件 ═══════════════════════ */
function eventToCanvas(e) {
  const rect = canvas.getBoundingClientRect();
  const px = (e.clientX - rect.left) * (boardPx() / rect.width);
  const py = (e.clientY - rect.top) * (boardPx() / rect.height);
  return [px, py];
}

canvas.addEventListener("click", (e) => {
  const [px, py] = eventToCanvas(e);
  const pos = toGrid(px, py);
  if (!pos) return;
  if (mode === "scoring") {
    handleScoringClick(pos[0], pos[1]);
  } else {
    tryPlay(pos[0], pos[1]);
  }
});

canvas.addEventListener("mousemove", (e) => {
  const [px, py] = eventToCanvas(e);
  const np = toGrid(px, py);
  const same = np && hoverPos && np[0] === hoverPos[0] && np[1] === hoverPos[1];
  if (!same) {
    hoverPos = np;
    render();
  }
});

canvas.addEventListener("mouseleave", () => {
  hoverPos = null;
  render();
});

btnPass.addEventListener("click", doPass);
btnEnd.addEventListener("click", doEndGame);
btnResign.addEventListener("click", doResign);
btnUndo.addEventListener("click", doUndo);
btnPrev.addEventListener("click", () => jumpTo(navPos - 1));
btnNext.addEventListener("click", () => jumpTo(navPos + 1));
btnNew.addEventListener("click", doNewGame);
btnAutodead.addEventListener("click", autoDetectAgain);
btnConfirm.addEventListener("click", () => {
  if (mode !== "scoring" || scoringLocked) return;
  if (!confirm("确认当前结果为最终结果吗？")) return;
  scoringLocked = true;
  netSend({ type: "confirm", s: buildSync() });
  render();
  updatePanel();
});
btnResume.addEventListener("click", () => {
  if (mode !== "scoring" || scoringLocked) return;
  if (!confirm("返回对局继续下棋？")) return;
  resumeFromScoring();
  netSend({ type: "resume", s: buildSync() });
});

btnCreateRoom.addEventListener("click", createRoom);
btnJoinRoom.addEventListener("click", () => joinBox.classList.toggle("hidden"));
btnDoJoin.addEventListener("click", () => {
  joinRoom(roomInput.value);
  joinBox.classList.add("hidden");
});
roomInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    joinRoom(roomInput.value);
    joinBox.classList.add("hidden");
  }
});
btnLeaveNet.addEventListener("click", leaveNet);
btnNetCheck.addEventListener("click", checkNetwork);

boardSel.addEventListener("change", () => {
  if (netState !== "local") {
    flashHint("联机中不能切换棋盘");
    return;
  }
  const v = boardSel.value;
  if (v === "custom") {
    boardFile.click();
    return;
  }
  const idx = parseInt(v, 10);
  if (Number.isInteger(idx) && BOARD_PRESETS[idx]) {
    applyBoardConfig(BOARD_PRESETS[idx]);
  }
});

btnImport.addEventListener("click", () => boardFile.click());
boardFile.addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      const cfg = normalizeBoard(data);
      applyBoardConfig(cfg);
      flashHint("已导入棋盘：" + cfg.name);
    } catch (err) {
      flashHint("棋盘文件解析失败：" + err.message);
    }
  };
  reader.readAsText(f);
  e.target.value = "";
});

/* ═══════════════════════ 初始化 ═══════════════════════ */
function init() {
  versionEl.textContent = APP_VERSION;
  // 窗口尺寸变化时重算棋盘布局（手机横竖屏切换）
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("resize", () => {
      calcLayout();
      setupCanvas();
      render();
    });
  }
  // 下拉框（末尾追加"自定义…"占位）
  for (let i = 0; i < BOARD_PRESETS.length; i++) {
    const o = document.createElement("option");
    o.value = String(i);
    o.textContent = BOARD_PRESETS[i].name;
    boardSel.appendChild(o);
  }
  const customOpt = document.createElement("option");
  customOpt.value = "custom";
  customOpt.textContent = "自定义棋盘…";
  boardSel.appendChild(customOpt);

  // 恢复上次选择的棋盘
  let idx = parseInt(localStorage.getItem("gogame-board"), 10);
  if (!Number.isInteger(idx) || idx < 0 || idx >= BOARD_PRESETS.length) idx = 0;
  boardSel.value = String(idx);
  newGameWith(BOARD_PRESETS[idx]);
}

init();
