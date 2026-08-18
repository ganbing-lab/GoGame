/* ============================================================
 * engine.js — 围棋规则引擎（纯逻辑，无 DOM 依赖）
 * 移植自桌面版 gogame/core.py，支持异形棋盘（disabled 禁用格）。
 * 浏览器与 Node.js 均可加载（Node 用于单元测试）。
 *
 * 规则：黑先白后；落子提子；自杀禁止；打劫（positional superko，
 * 单步）；虚手（连续两虚终局）；数目法 / 数子法；自动死子检测
 * （两轮：边缘可达性 + 领地感知，双活需手动调整）。
 * ============================================================ */
"use strict";

const COLOR_EMPTY = 0;
const COLOR_BLACK = 1;
const COLOR_WHITE = 2;
const MARK_NEUTRAL = 3;
const KOMI = 6.5; // 白方贴目（数目法单位：目；数子法半贴 3.25 子）

const gkey = (r, c) => r + "," + c;
const opponentOf = (color) => (color === COLOR_BLACK ? COLOR_WHITE : COLOR_BLACK);

class GoGame {
  /**
   * @param {Object} config { name, size, disabled: [[r,c],...] }
   */
  constructor(config) {
    config = config || {};
    this.name = config.name || "棋盘";
    this.size = (config.size > 1 && config.size <= 25) ? config.size : 19;
    this.disabled = new Set();
    for (const p of (config.disabled || [])) {
      if (Array.isArray(p) && p.length >= 2 && this.inRange(p[0], p[1])) {
        this.disabled.add(gkey(p[0], p[1]));
      }
    }
    this.reset();
  }

  inRange(r, c) {
    return r >= 0 && r < this.size && c >= 0 && c < this.size;
  }

  reset() {
    const n = this.size;
    this.board = [];
    for (let r = 0; r < n; r++) this.board.push(new Array(n).fill(COLOR_EMPTY));
    this.current = COLOR_BLACK;
    this.captured = { [COLOR_BLACK]: 0, [COLOR_WHITE]: 0 };
    this.prevBoard = null;   // 打劫检查：上一手落子前的局面
    this.passCount = 0;
    this.gameOver = false;
    this.winner = null;
    this.moves = [];         // {r, c, color}，r=-1 表示虚手
  }

  // ───────────── 图论工具 ─────────────
  inBounds(r, c) {
    return this.inRange(r, c) && !this.disabled.has(gkey(r, c));
  }

  neighbors(r, c) {
    const out = [];
    for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const nr = r + dr, nc = c + dc;
      if (this.inBounds(nr, nc)) out.push([nr, nc]);
    }
    return out;
  }

  /** 同色棋串 */
  group(r, c) {
    const color = this.board[r][c];
    if (color === COLOR_EMPTY) return [];
    const visited = new Set(), stack = [[r, c]];
    while (stack.length) {
      const [cr, cc] = stack.pop();
      const k = gkey(cr, cc);
      if (visited.has(k)) continue;
      visited.add(k);
      for (const [nr, nc] of this.neighbors(cr, cc)) {
        if (this.board[nr][nc] === color && !visited.has(gkey(nr, nc))) stack.push([nr, nc]);
      }
    }
    return [...visited].map((k) => k.split(",").map(Number));
  }

  /** 棋串的气 */
  liberties(r, c) {
    const color = this.board[r][c];
    if (color === COLOR_EMPTY) return [];
    const visited = new Set(), libs = new Set(), stack = [[r, c]];
    while (stack.length) {
      const [cr, cc] = stack.pop();
      const k = gkey(cr, cc);
      if (visited.has(k)) continue;
      visited.add(k);
      for (const [nr, nc] of this.neighbors(cr, cc)) {
        const cell = this.board[nr][nc];
        if (cell === COLOR_EMPTY) libs.add(gkey(nr, nc));
        else if (cell === color && !visited.has(gkey(nr, nc))) stack.push([nr, nc]);
      }
    }
    return [...libs].map((k) => k.split(",").map(Number));
  }

  snapshot() {
    return this.board.map((row) => row.slice());
  }

  static boardEq(a, b) {
    if (!a || !b) return false;
    for (let r = 0; r < a.length; r++) {
      for (let c = 0; c < a[r].length; c++) {
        if (a[r][c] !== b[r][c]) return false;
      }
    }
    return true;
  }

  // ───────────── 落子合法性 ─────────────
  isLegal(r, c) {
    if (this.gameOver) return false;
    if (!this.inBounds(r, c) || this.board[r][c] !== COLOR_EMPTY) return false;
    const me = this.current, opp = opponentOf(me);
    const saved = this.snapshot();
    this.board[r][c] = me;

    // 是否提掉邻接敌子
    let captures = false;
    for (const [nr, nc] of this.neighbors(r, c)) {
      if (this.board[nr][nc] === opp && this.liberties(nr, nc).length === 0) {
        captures = true;
        break;
      }
    }
    // 自杀禁止
    if (!captures && this.liberties(r, c).length === 0) {
      this.board = saved;
      return false;
    }
    // 模拟提子
    const capturedCells = [];
    for (const [nr, nc] of this.neighbors(r, c)) {
      if (this.board[nr][nc] === opp && this.liberties(nr, nc).length === 0) {
        for (const [gr, gc] of this.group(nr, nc)) capturedCells.push([gr, gc]);
      }
    }
    for (const [gr, gc] of capturedCells) this.board[gr][gc] = COLOR_EMPTY;
    // 打劫：落子后局面不得与上一手之前相同
    const ko = GoGame.boardEq(this.board, this.prevBoard);
    this.board = saved;
    return !ko;
  }

  /** 落子。返回提子数；非法返回 -1。 */
  play(r, c) {
    if (!this.isLegal(r, c)) return -1;
    this.prevBoard = this.snapshot();
    const me = this.current, opp = opponentOf(me);
    this.board[r][c] = me;
    this.passCount = 0;
    let taken = 0;
    for (const [nr, nc] of this.neighbors(r, c)) {
      if (this.board[nr][nc] === opp && this.liberties(nr, nc).length === 0) {
        const grp = this.group(nr, nc);
        taken += grp.length;
        for (const [gr, gc] of grp) this.board[gr][gc] = COLOR_EMPTY;
      }
    }
    this.captured[me] += taken;
    this.moves.push({ r, c, color: me });
    this.current = opp;
    return taken;
  }

  /** 虚手。连续两虚终局返回 true。 */
  passMove() {
    this.passCount += 1;
    this.moves.push({ r: -1, c: -1, color: this.current });
    this.current = opponentOf(this.current);
    if (this.passCount >= 2) {
      this.gameOver = true;
      return true;
    }
    return false;
  }

  resign() {
    this.gameOver = true;
    this.winner = opponentOf(this.current);
  }

  /**
   * 回放到第 n 手（0 <= n <= moves.length）。从空棋盘重放前 n 手，
   * 用于翻棋导航 / 悔棋。返回实际回放手数。
   */
  replayTo(n) {
    n = Math.max(0, Math.min(n, this.moves.length));
    const savedMoves = this.moves.slice();
    this.reset();
    this.moves = savedMoves;
    for (let i = 0; i < n; i++) {
      const m = this.moves[i];
      this.current = m.color;
      if (m.r === -1) {
        this.passCount += 1;
        this.current = opponentOf(m.color);
      } else {
        this.prevBoard = this.snapshot();
        this.board[m.r][m.c] = m.color;
        this.passCount = 0;
        const opp = opponentOf(m.color);
        for (const [nr, nc] of this.neighbors(m.r, m.c)) {
          if (this.board[nr][nc] === opp && this.liberties(nr, nc).length === 0) {
            const grp = this.group(nr, nc);
            this.captured[m.color] += grp.length;
            for (const [gr, gc] of grp) this.board[gr][gc] = COLOR_EMPTY;
          }
        }
        this.current = opp;
      }
    }
    return n;
  }

  // ───────────── 终局计分 ─────────────
  /**
   * 空点连通区域（死子视为空）。
   * deadSet: Set<"r,c"> 死子坐标。
   */
  emptyRegionAt(r, c, deadSet) {
    if (!this.inBounds(r, c)) return [];
    const k0 = gkey(r, c);
    if (this.board[r][c] !== COLOR_EMPTY && !deadSet.has(k0)) return [];
    const visited = new Set(), stack = [[r, c]];
    while (stack.length) {
      const [cr, cc] = stack.pop();
      const k = gkey(cr, cc);
      if (visited.has(k)) continue;
      visited.add(k);
      for (const [nr, nc] of this.neighbors(cr, cc)) {
        const kk = gkey(nr, nc);
        const cell = this.board[nr][nc];
        if ((cell === COLOR_EMPTY || deadSet.has(kk)) && !visited.has(kk)) {
          stack.push([nr, nc]);
        }
      }
    }
    return [...visited].map((k) => k.split(",").map(Number));
  }

  /** 领地区域：返回 {黑:Set, 白:Set} 归属的空点集合（含死子当空）。 */
  territoryRegions(deadSet) {
    deadSet = deadSet || new Set();
    const regions = { [COLOR_BLACK]: new Set(), [COLOR_WHITE]: new Set() };
    const visited = new Set();
    for (let r = 0; r < this.size; r++) {
      for (let c = 0; c < this.size; c++) {
        const k = gkey(r, c);
        const open = this.board[r][c] === COLOR_EMPTY || deadSet.has(k);
        if (!open || visited.has(k)) continue;
        const region = this.emptyRegionAt(r, c, deadSet);
        for (const [rr, cc] of region) visited.add(gkey(rr, cc));
        const borders = new Set();
        for (const [rr, cc] of region) {
          for (const [nr, nc] of this.neighbors(rr, cc)) {
            const cell = this.board[nr][nc];
            if (cell !== COLOR_EMPTY && !deadSet.has(gkey(nr, nc))) borders.add(cell);
          }
        }
        if (borders.size === 1) {
          const owner = [...borders][0];
          for (const [rr, cc] of region) regions[owner].add(gkey(rr, cc));
        }
      }
    }
    return regions;
  }

  /** 领地计数：{black: n, white: n} */
  territory(deadSet) {
    const r = this.territoryRegions(deadSet);
    return { [COLOR_BLACK]: r[COLOR_BLACK].size, [COLOR_WHITE]: r[COLOR_WHITE].size };
  }

  /** 手动标记计分：BLACK→黑+1, WHITE→白+1, NEUTRAL→各+0.5 */
  static scoreFromMarks(marks) {
    let b = 0, w = 0;
    for (const owner of marks.values()) {
      if (owner === COLOR_BLACK) b += 1;
      else if (owner === COLOR_WHITE) w += 1;
      else if (owner === MARK_NEUTRAL) { b += 0.5; w += 0.5; }
    }
    return [b, w];
  }

  /** 数目法（日本）：目 + 提子，白贴 KOMI 目 */
  scoreJapanese(deadSet) {
    const terr = this.territory(deadSet);
    return {
      black: terr[COLOR_BLACK] + this.captured[COLOR_BLACK],
      white: terr[COLOR_WHITE] + this.captured[COLOR_WHITE] + KOMI,
      territory: terr,
    };
  }

  /** 数子法（中国）：活子 + 目，白贴 KOMI/2 子 */
  scoreChinese(deadSet) {
    const terr = this.territory(deadSet);
    let liveB = 0, liveW = 0;
    for (let r = 0; r < this.size; r++) {
      for (let c = 0; c < this.size; c++) {
        const cell = this.board[r][c];
        if (cell !== COLOR_EMPTY && !deadSet.has(gkey(r, c))) {
          if (cell === COLOR_BLACK) liveB++; else liveW++;
        }
      }
    }
    return {
      black: liveB + terr[COLOR_BLACK],
      white: liveW + terr[COLOR_WHITE] + KOMI / 2,
      territory: terr,
      live: { [COLOR_BLACK]: liveB, [COLOR_WHITE]: liveW },
    };
  }

  // ───────────── 自动死子检测 ─────────────
  /**
   * 两轮迭代消除：
   *  第一轮 边缘可达性：棋串不能经空点/死子到达棋盘边缘，
   *         且独享眼区 < 2 → 判死（死子视为空，迭代至稳定）。
   *  第二轮 领地感知：补充第一轮漏掉的、被对手领地完全封锁的棋串。
   * 注：双活（seki）无法自动处理，需在计分阶段手动调整。
   * @returns {Set<string>} "r,c" 死子坐标
   */
  autoDetectDead() {
    const dead = new Set();
    const n = this.size;

    const allStrings = () => {
      const seen = new Set(), strings = [];
      for (let r = 0; r < n; r++) {
        for (let c = 0; c < n; c++) {
          const k = gkey(r, c);
          if (this.board[r][c] !== COLOR_EMPTY && !seen.has(k)) {
            const grp = this.group(r, c);
            for (const [rr, cc] of grp) seen.add(gkey(rr, cc));
            strings.push({ color: this.board[r][c], cells: grp });
          }
        }
      }
      return strings;
    };

    // 棋串能否经空点/死子到达棋盘边缘
    const canReachEdge = (cells) => {
      const visited = new Set(cells.map(([rr, cc]) => gkey(rr, cc)));
      const stack = cells.slice();
      while (stack.length) {
        const [cr, cc] = stack.pop();
        if (cr === 0 || cr === n - 1 || cc === 0 || cc === n - 1) return true;
        for (const [nr, nc] of this.neighbors(cr, cc)) {
          const k = gkey(nr, nc);
          if (visited.has(k)) continue;
          const cell = this.board[nr][nc];
          if (cell === COLOR_EMPTY || dead.has(k)) { visited.add(k); stack.push([nr, nc]); }
        }
      }
      return false;
    };

    // 独享眼数：与该棋串相邻、边界全为该棋串颜色的空区域数量
    const eyeCount = (cells, color) => {
      const adj = new Set();
      for (const [cr, cc] of cells) {
        for (const [nr, nc] of this.neighbors(cr, cc)) {
          const k = gkey(nr, nc);
          if (this.board[nr][nc] === COLOR_EMPTY || dead.has(k)) adj.add(k);
        }
      }
      const seenEmpty = new Set();
      let eyes = 0;
      for (const ak of adj) {
        if (seenEmpty.has(ak)) continue;
        const [ar, ac] = ak.split(",").map(Number);
        const region = this.emptyRegionAt(ar, ac, dead);
        for (const [rr, cc] of region) seenEmpty.add(gkey(rr, cc));
        let pure = true;
        for (const [rr, cc] of region) {
          for (const [nr, nc] of this.neighbors(rr, cc)) {
            const cell = this.board[nr][nc];
            if (cell !== COLOR_EMPTY && !dead.has(gkey(nr, nc)) && cell !== color) {
              pure = false;
              break;
            }
          }
          if (!pure) break;
        }
        if (pure) eyes++;
      }
      return eyes;
    };

    // 第一轮：边缘可达性
    for (let iter = 0; iter < 8; iter++) {
      let changed = false;
      for (const s of allStrings()) {
        const fullyDead = s.cells.every(([rr, cc]) => dead.has(gkey(rr, cc)));
        if (fullyDead) continue;
        if (!canReachEdge(s.cells) && eyeCount(s.cells, s.color) < 2) {
          for (const [rr, cc] of s.cells) dead.add(gkey(rr, cc));
          changed = true;
        }
      }
      if (!changed) break;
    }

    // 第二轮：领地感知
    for (let iter = 0; iter < 8; iter++) {
      const terr = this.territoryRegions(dead);
      let changed = false;
      for (const s of allStrings()) {
        const fullyDead = s.cells.every(([rr, cc]) => dead.has(gkey(rr, cc)));
        if (fullyDead) continue;
        const opp = opponentOf(s.color);
        // 出口：棋串相邻的空点/死子
        const exits = new Set();
        for (const [cr, cc] of s.cells) {
          for (const [nr, nc] of this.neighbors(cr, cc)) {
            const k = gkey(nr, nc);
            const cell = this.board[nr][nc];
            if (cell === COLOR_EMPTY || dead.has(k)) exits.add(k);
          }
        }
        // 全部出口都通往对手领地（无出口 = 完全被围死）
        const allToOpp = [...exits].every((k) => terr[opp].has(k));
        if (allToOpp && eyeCount(s.cells, s.color) < 2) {
          for (const [rr, cc] of s.cells) dead.add(gkey(rr, cc));
          changed = true;
        }
      }
      if (!changed) break;
    }

    return dead;
  }
}

// Node.js 环境导出（浏览器中则作为全局类使用）
if (typeof module !== "undefined" && module.exports) {
  module.exports = { GoGame, COLOR_EMPTY, COLOR_BLACK, COLOR_WHITE, MARK_NEUTRAL, KOMI, gkey, opponentOf };
}
