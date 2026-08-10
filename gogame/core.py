"""
围棋核心逻辑：落子、提子、打劫、虚手、数目 / 数子。
完全不依赖 UI 框架，可被任何前端（Tkinter / Pygame / Web）复用。
"""

from .config import BOARD_SIZE, COLOR_EMPTY, COLOR_BLACK, COLOR_WHITE, MARK_NEUTRAL, KOMI


class GoGame:
    """围棋核心引擎"""

    def __init__(self):
        self.board = [[COLOR_EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.current = COLOR_BLACK
        self.captured = {COLOR_BLACK: 0, COLOR_WHITE: 0}
        self.prev_board = None               # 劫争用
        self.pass_count = 0
        self.game_over = False
        self.winner = None
        self.moves = []                      # [(r, c, color)] or (-1, -1, color) for pass

    # ──────────────────────────────────────────────
    #  基础图论工具
    # ──────────────────────────────────────────────
    @staticmethod
    def _in_bounds(r, c):
        return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE

    def _neighbors(self, r, c):
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if self._in_bounds(nr, nc):
                yield nr, nc

    def _group(self, r, c):
        """返回 (r,c) 所在同色棋串的全部坐标"""
        color = self.board[r][c]
        if color == COLOR_EMPTY:
            return set()
        visited, stack = set(), [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in visited:
                continue
            visited.add((cr, cc))
            for nr, nc in self._neighbors(cr, cc):
                if self.board[nr][nc] == color and (nr, nc) not in visited:
                    stack.append((nr, nc))
        return visited

    def _empty_region(self, r, c):
        """返回 (r,c) 所在连通空地区域的全部坐标（仅限空点）"""
        if self.board[r][c] != COLOR_EMPTY:
            return set()
        visited, stack = set(), [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in visited:
                continue
            visited.add((cr, cc))
            for nr, nc in self._neighbors(cr, cc):
                if self.board[nr][nc] == COLOR_EMPTY and (nr, nc) not in visited:
                    stack.append((nr, nc))
        return visited

    def _liberties(self, r, c):
        """返回 (r,c) 所在棋串的全部气"""
        color = self.board[r][c]
        if color == COLOR_EMPTY:
            return set()
        visited = set()
        liberties = set()
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if (cr, cc) in visited:
                continue
            visited.add((cr, cc))
            for nr, nc in self._neighbors(cr, cc):
                if self.board[nr][nc] == COLOR_EMPTY:
                    liberties.add((nr, nc))
                elif self.board[nr][nc] == color and (nr, nc) not in visited:
                    stack.append((nr, nc))
        return liberties

    def _snapshot(self):
        return [row[:] for row in self.board]

    @staticmethod
    def _board_eq(a, b):
        if a is None or b is None:
            return False
        return all(a[i] == b[i] for i in range(BOARD_SIZE))

    # ──────────────────────────────────────────────
    #  落子合法性
    # ──────────────────────────────────────────────
    def is_valid(self, r, c):
        """检查 (r,c) 是否合法落子点"""
        if self.game_over:
            return False
        if not self._in_bounds(r, c) or self.board[r][c] != COLOR_EMPTY:
            return False

        opponent = COLOR_WHITE if self.current == COLOR_BLACK else COLOR_BLACK

        saved = self._snapshot()
        self.board[r][c] = self.current

        # 检查是否提掉邻接敌子
        captures_happen = False
        for nr, nc in self._neighbors(r, c):
            if self.board[nr][nc] == opponent and len(self._liberties(nr, nc)) == 0:
                captures_happen = True
                break

        # 自杀禁止
        if not captures_happen and len(self._liberties(r, c)) == 0:
            self.board = saved
            return False

        # 模拟提子
        captured = []
        for nr, nc in self._neighbors(r, c):
            if self.board[nr][nc] == opponent:
                if len(self._liberties(nr, nc)) == 0:
                    captured.extend(self._group(nr, nc))
        for gr, gc in captured:
            self.board[gr][gc] = COLOR_EMPTY

        # 打劫（positional superko - 单步）
        ko = self._board_eq(self.board, self.prev_board)
        self.board = saved
        return not ko

    # ──────────────────────────────────────────────
    #  落子 / 虚手 / 认输
    # ──────────────────────────────────────────────
    def play(self, r, c):
        """落子。返回提子数；非法返回 -1。"""
        if not self.is_valid(r, c):
            return -1

        self.prev_board = self._snapshot()

        opponent = COLOR_WHITE if self.current == COLOR_BLACK else COLOR_BLACK
        self.board[r][c] = self.current
        self.pass_count = 0

        taken = 0
        for nr, nc in self._neighbors(r, c):
            if self.board[nr][nc] == opponent:
                if len(self._liberties(nr, nc)) == 0:
                    grp = self._group(nr, nc)
                    taken += len(grp)
                    for gr, gc in grp:
                        self.board[gr][gc] = COLOR_EMPTY
        self.captured[self.current] += taken
        self.moves.append((r, c, self.current))
        self.current = opponent
        return taken

    def pass_move(self):
        """虚手。连续两虚终局返回 True。"""
        self.pass_count += 1
        self.moves.append((-1, -1, self.current))
        self.current = COLOR_WHITE if self.current == COLOR_BLACK else COLOR_BLACK
        if self.pass_count >= 2:
            self.game_over = True
            return True
        return False

    def resign(self):
        self.game_over = True
        self.winner = COLOR_WHITE if self.current == COLOR_BLACK else COLOR_BLACK

    def reset(self):
        self.__init__()

    def set_position(self, n):
        """回退到第 n 手（0 <= n <= len(moves)）。
        从空棋盘回放前 n 手到 board。不会添加新的 moves 记录。
        n == len(moves) 时恢复完整棋局。
        每次调用都是重新回放（不是增量）。
        """
        n = max(0, min(n, len(self.moves)))
        saved = self.moves[:]
        self.board = [[COLOR_EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.captured = {COLOR_BLACK: 0, COLOR_WHITE: 0}
        self.prev_board = None
        self.pass_count = 0
        self.game_over = False
        self.winner = None
        self.current = COLOR_BLACK
        self.moves = saved  # preserve full history

        for i in range(n):
            r, c, color = saved[i]
            self.current = color
            if r == -1:
                self.pass_count += 1
                self.current = COLOR_WHITE if self.current == COLOR_BLACK else COLOR_BLACK
            else:
                self.prev_board = [row[:] for row in self.board]
                self.board[r][c] = color
                self.pass_count = 0
                opponent = COLOR_WHITE if color == COLOR_BLACK else COLOR_BLACK
                for nr, nc in self._neighbors(r, c):
                    if self.board[nr][nc] == opponent:
                        if len(self._liberties(nr, nc)) == 0:
                            grp = self._group(nr, nc)
                            self.captured[color] += len(grp)
                            for gr, gc in grp:
                                self.board[gr][gc] = COLOR_EMPTY
                self.current = opponent
        return n

    # ──────────────────────────────────────────────
    #  手动标记的连通区域（用于终局计分）
    # ──────────────────────────────────────────────
    def mark_region_at(self, r, c):
        """返回 (r,c) 所在连通区域的全部坐标。
        空点区域用 _empty_region，棋子区域用 _group。"""
        if self.board[r][c] == COLOR_EMPTY:
            return self._empty_region(r, c)
        return self._group(r, c)

    # ──────────────────────────────────────────────
    #  基于 marks 的计分
    #  marks: {(r,c): COLOR_BLACK|COLOR_WHITE|MARK_NEUTRAL}
    #  未标记的点 = 不计入任何人
    # ──────────────────────────────────────────────
    @staticmethod
    def score_from_marks(marks):
        """从手动标记结果计分。
        BLACK 点 → 黑 +1, WHITE 点 → 白 +1, NEUTRAL → 各 +0.5。"""
        black = 0.0
        white = 0.0
        for (r, c), owner in marks.items():
            if owner == COLOR_BLACK:
                black += 1
            elif owner == COLOR_WHITE:
                white += 1
            elif owner == MARK_NEUTRAL:
                black += 0.5
                white += 0.5
        return black, white

    # ──────────────────────────────────────────────
    #  局面评估（保留供参考，新流程以 marks 为准）
    # ──────────────────────────────────────────────
    def territory(self, dead_stones=None):
        """
        种子填充计算目数。
        dead_stones: set of (r,c) 死子坐标，视为空点。
        """
        if dead_stones is None:
            dead_stones = set()

        result = {COLOR_BLACK: 0, COLOR_WHITE: 0}
        visited = set()

        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                is_empty = self.board[r][c] == COLOR_EMPTY
                is_dead = (r, c) in dead_stones
                if (is_empty or is_dead) and (r, c) not in visited:
                    region = set()
                    border_colors = set()
                    stack = [(r, c)]
                    while stack:
                        cr, cc = stack.pop()
                        if (cr, cc) in visited:
                            continue
                        visited.add((cr, cc))
                        region.add((cr, cc))
                        for nr, nc in self._neighbors(cr, cc):
                            cell = self.board[nr][nc]
                            pos = (nr, nc)
                            if (cell == COLOR_EMPTY or pos in dead_stones) and pos not in visited:
                                stack.append(pos)
                            elif cell != COLOR_EMPTY and pos not in dead_stones:
                                border_colors.add(cell)
                    if len(border_colors) == 1:
                        result[border_colors.pop()] += len(region)
        return result

    def score_japanese(self, dead_stones=None):
        """数目法（日本规则）：目 + 提子，不计活子"""
        if dead_stones is None:
            dead_stones = set()
        terr = self.territory(dead_stones)
        black = terr[COLOR_BLACK] + self.captured[COLOR_BLACK]
        white = terr[COLOR_WHITE] + self.captured[COLOR_WHITE] + KOMI
        return black, white, terr

    def score_chinese(self, dead_stones=None):
        """数子法（中国规则）：活子 + 目 + 贴目(KOMI/2)。
        KOMI 定义了 6.5 目（日本单位），中式单位为子（1 子 ≈ 2 目），
        因此贴目为 KOMI/2 = 3.25 子。"""
        if dead_stones is None:
            dead_stones = set()

        live = {COLOR_BLACK: 0, COLOR_WHITE: 0}
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell = self.board[r][c]
                if cell != COLOR_EMPTY and (r, c) not in dead_stones:
                    live[cell] += 1

        terr = self.territory(dead_stones)
        black = live[COLOR_BLACK] + terr[COLOR_BLACK]
        white = live[COLOR_WHITE] + terr[COLOR_WHITE] + KOMI / 2
        return black, white, terr, live
