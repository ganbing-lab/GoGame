/* ============================================================
 * engine.test.js — 规则引擎单元测试（Node.js）
 * 运行：node docs/tests/engine.test.js
 * 覆盖：提子 / 自杀禁止 / 打劫 / 虚手终局 / 翻棋回放 /
 *       异形棋盘边界 / 自动死子检测 / 数目法·数子法
 * ============================================================ */
"use strict";

const assert = require("assert");
const { GoGame, COLOR_EMPTY, COLOR_BLACK, COLOR_WHITE, KOMI, gkey } = require("../engine.js");

let passed = 0;
function ok(name, fn) {
  try {
    fn();
    passed++;
    console.log("  ✓ " + name);
  } catch (e) {
    console.error("  ✗ " + name + "\n    " + (e && e.message));
    process.exitCode = 1;
  }
}
function eq(a, b, msg) {
  assert.strictEqual(a, b, msg || (a + " !== " + b));
}

console.log("═ 规则引擎测试 ═");

// ── 1. 提子 ──
ok("提子：黑提角上单子白", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  eq(g.play(17, 18), 0);   // 黑
  eq(g.play(18, 18), 0);   // 白（角）
  eq(g.play(18, 17), 1);   // 黑提白
  eq(g.board[18][18], COLOR_EMPTY);
  eq(g.captured[COLOR_BLACK], 1);
});

// ── 2. 自杀禁止 ──
ok("自杀禁止：无气且不提子时不能落子", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  g.board[0][1] = COLOR_BLACK;
  g.board[1][0] = COLOR_BLACK;
  g.board[0][2] = COLOR_WHITE;
  g.board[1][1] = COLOR_WHITE;
  g.board[2][0] = COLOR_WHITE;
  g.board[2][1] = COLOR_WHITE;
  g.current = COLOR_BLACK;
  // (0,0) 邻 (0,1)黑 (1,0)黑，无气且不提子 → 自杀
  eq(g.isLegal(0, 0), false);
  eq(g.play(0, 0), -1);
  eq(g.board[0][0], COLOR_EMPTY);
});

// ── 3. 打劫 ──
ok("打劫：提回被禁止（positional superko）", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  // 标准单劫（角部）：
  //   白 (0,2)(1,1)，黑 (1,0)，白 (0,0)，劫点 (0,1) 空
  //   黑在 (0,1) 落子提白(0,0) 后，黑劫子与同色不连通、只剩
  //   (0,0) 一口气；白在 (0,0) 落子提回黑劫子将使局面完全复原 → ko
  g.board[0][2] = COLOR_WHITE;
  g.board[1][1] = COLOR_WHITE;
  g.board[1][0] = COLOR_BLACK;
  g.board[0][0] = COLOR_WHITE;
  eq(g.liberties(0, 0).length, 1, "白(0,0)应只有 1 气");
  g.current = COLOR_BLACK;
  eq(g.play(0, 1), 1, "黑在劫点落子提白");
  eq(g.board[0][0], COLOR_EMPTY);
  eq(g.current, COLOR_WHITE);
  eq(g.liberties(0, 1).length, 1, "黑劫子只剩 1 气");
  eq(g.isLegal(0, 0), false, "白不能立刻提回（劫）");
  eq(g.play(0, 0), -1);
  // 隔一手后可以提回
  eq(g.play(9, 9), 0, "白下别处（隔手）");
  eq(g.play(9, 8), 0, "黑应一手");
  eq(g.current, COLOR_WHITE, "轮到白");
  eq(g.isLegal(0, 0), true, "隔手后可提回劫");
  eq(g.play(0, 0), 1, "白提回黑劫子");
  eq(g.board[0][0], COLOR_WHITE);
  eq(g.board[0][1], COLOR_EMPTY, "黑劫子被提");
});

// ── 4. 虚手双终局 ──
ok("虚手：连续两虚手终局", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  g.play(3, 3);
  eq(g.passMove(), false);
  eq(g.passMove(), true);
  eq(g.gameOver, true);
});

// ── 5. 翻棋回放 ──
ok("翻棋回放：replayTo 重建历史局面", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  g.play(3, 3);
  g.play(3, 4);
  g.play(4, 3);
  g.play(15, 15);
  const full = g.snapshot();
  g.replayTo(2);
  eq(g.board[3][3], COLOR_BLACK);
  eq(g.board[3][4], COLOR_WHITE);
  eq(g.board[4][3], COLOR_EMPTY);
  eq(g.current, COLOR_BLACK);
  g.replayTo(4);
  assert.deepStrictEqual(g.board, full, "回放回完整局面应一致");
});

// ── 6. 异形棋盘 ──
ok("异形棋盘：禁用格不可落子、不算气", () => {
  const g = new GoGame({ name: "天元孤岛", size: 19, disabled: [[9, 9]] });
  eq(g.isLegal(9, 9), false, "禁用格不能落子");
  g.play(9, 8);            // 黑
  const libs = g.liberties(9, 8);
  const keys = libs.map(([r, c]) => gkey(r, c));
  eq(keys.includes("9,9"), false, "禁用格不算气");
  eq(libs.length, 3, "天元旁的黑子应恰好 3 气");
  // 可落点计数
  let n = 0;
  for (let r = 0; r < 19; r++) for (let c = 0; c < 19; c++) if (g.isLegal(r, c)) n++;
  eq(n, 359, "19 路挖 1 格应有 359 个合法点（黑先）");
});

// ── 7. 自动死子检测 ──
ok("死子检测：被围一子判死", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  // 黑(9,9)被白三面包围，唯一一口气 (9,10) 也是被白围死的孤立空点
  g.board[8][9] = COLOR_WHITE;
  g.board[9][8] = COLOR_WHITE;
  g.board[10][9] = COLOR_WHITE;
  g.board[8][10] = COLOR_WHITE;
  g.board[10][10] = COLOR_WHITE;
  g.board[9][11] = COLOR_WHITE;
  g.board[9][9] = COLOR_BLACK;
  eq(g.liberties(9, 9).length, 1, "黑(9,9)应只有 1 气");
  const dead = g.autoDetectDead();
  eq(dead.has("9,9"), true, "黑(9,9) 应判死");
});

ok("死子检测：两眼活棋不判死", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  for (let r = 0; r <= 4; r++) {
    for (let c = 0; c <= 4; c++) {
      g.board[r][c] = COLOR_BLACK;
    }
  }
  g.board[1][1] = COLOR_EMPTY;   // 眼 1
  g.board[3][3] = COLOR_EMPTY;   // 眼 2
  const dead = g.autoDetectDead();
  eq(dead.has("0,0"), false, "能到边缘的棋串不应判死");
  eq(dead.size, 0);
});

ok("死子检测：异形棋盘上不崩溃且结果合理", () => {
  const g = new GoGame({ name: "迷宫", size: 19, disabled: [[9, 9], [9, 8], [8, 9]] });
  g.board[10][10] = COLOR_BLACK;
  g.board[9][10] = COLOR_WHITE;
  g.board[10][9] = COLOR_WHITE;
  const dead = g.autoDetectDead();
  assert(dead instanceof Set, "返回 Set");
});

// ── 8. 计分 ──
ok("数子法：左右分投计分", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  for (let r = 0; r < 19; r++) {
    for (let c = 0; c < 9; c++) g.board[r][c] = COLOR_BLACK;
    for (let c = 10; c < 19; c++) g.board[r][c] = COLOR_WHITE;
  }
  // 第 9 列空（双方交界，不计入）
  const dead = new Set();
  const cn = g.scoreChinese(dead);
  eq(cn.black, 171, "黑活子 171");
  eq(cn.white, 171 + KOMI / 2, "白 171 + 贴 3.25");
  const jp = g.scoreJapanese(dead);
  eq(jp.black, 0, "数目法：无领地（交界列不属任何方）");
  eq(jp.white, KOMI, "数目法：白只有贴目");
});

ok("数目法：死子当空计入对方领地", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  // 白全占 6..12 列
  for (let r = 0; r < 19; r++) {
    for (let c = 6; c <= 12; c++) g.board[r][c] = COLOR_WHITE;
  }
  g.board[9][9] = COLOR_BLACK;   // 白领地内的黑子（无气，判死）
  const base = g.territory(new Set());
  eq(base[COLOR_WHITE], 228, "无死子时白领地 = 左右空域 6+6 列");
  const dead = g.autoDetectDead();
  eq(dead.has("9,9"), true);
  const withDead = g.territory(dead);
  eq(withDead[COLOR_WHITE], 229, "死子当空后白领地 +1");
  const jp = g.scoreJapanese(dead);
  eq(jp.white, 229 + KOMI, "白 229 目 + 贴目");
  eq(jp.black, 0);
});

ok("手动标记计分：scoreFromMarks", () => {
  const marks = new Map();
  marks.set("0,0", COLOR_BLACK);
  marks.set("0,1", COLOR_WHITE);
  marks.set("0,2", 3); // MARK_NEUTRAL
  const [b, w] = GoGame.scoreFromMarks(marks);
  eq(b, 1.5);
  eq(w, 1.5);
});

// ── 9. 空区域连通（计分标记用）──
ok("空区域：死子视为空参与连通", () => {
  const g = new GoGame({ size: 19, disabled: [] });
  // 白围 3×3 环（8 子），内部 (9,9) 黑（无气）
  for (let c = 8; c <= 10; c++) { g.board[8][c] = COLOR_WHITE; g.board[10][c] = COLOR_WHITE; }
  g.board[9][8] = COLOR_WHITE;
  g.board[9][10] = COLOR_WHITE;
  g.board[9][9] = COLOR_BLACK;
  const dead = new Set(["9,9"]);
  const region = g.emptyRegionAt(9, 9, dead);
  eq(region.length, 1, "死子单独成 1 格空区域");
  const base = g.territory(new Set());
  eq(base[COLOR_WHITE], 352, "死子不当空时白领地 = 外部空域");
  const withDead = g.territory(dead);
  eq(withDead[COLOR_WHITE], 353, "死子当空后 +1 计入白领地");
  eq(withDead[COLOR_BLACK], 0);
});

console.log("\n" + (process.exitCode ? "✗ 存在失败用例" : "✓ 全部通过") + "（" + passed + " 个用例）");
