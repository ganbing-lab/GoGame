"""
棋盘 Canvas — 绘制棋盘、棋子、标记区域、鼠标悬停预览。
"""

import tkinter as tk

from .config import (
    BOARD_SIZE, CELL_SIZE, MARGIN, STONE_R, BOARD_PX,
    COLOR_BLACK, COLOR_WHITE, COLOR_EMPTY, MARK_NEUTRAL,
    BG_COLOR, LINE_COLOR, STAR_POINTS,
)


class BoardCanvas(tk.Canvas):
    """棋盘绘制与点击交互"""

    def __init__(self, parent, game, on_click):
        super().__init__(parent, width=BOARD_PX, height=BOARD_PX,
                         bg=BG_COLOR, highlightthickness=0, cursor="hand2")
        self.game = game
        self.on_click = on_click
        self.marks = {}            # {(r, c): COLOR_BLACK|COLOR_WHITE|MARK_NEUTRAL}
        self.hover_pos = None
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        self._draw_board()

    # ──────────────────────────────────────────────
    #  坐标转换
    # ──────────────────────────────────────────────
    def _to_grid(self, px, py):
        c = round((px - MARGIN) / CELL_SIZE)
        r = round((py - MARGIN) / CELL_SIZE)
        if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
            return r, c
        return None

    @staticmethod
    def _to_px(r, c):
        return MARGIN + c * CELL_SIZE, MARGIN + r * CELL_SIZE

    # ──────────────────────────────────────────────
    #  绘制静态元素
    # ──────────────────────────────────────────────
    def _draw_board(self):
        self.delete("grid")

        for i in range(BOARD_SIZE):
            y = MARGIN + i * CELL_SIZE
            self.create_line(MARGIN, y, MARGIN + CELL_SIZE * (BOARD_SIZE - 1), y,
                             fill=LINE_COLOR, width=1, tags="grid")
        for i in range(BOARD_SIZE):
            x = MARGIN + i * CELL_SIZE
            self.create_line(x, MARGIN, x, MARGIN + CELL_SIZE * (BOARD_SIZE - 1),
                             fill=LINE_COLOR, width=1, tags="grid")

        for r, c in STAR_POINTS:
            x, y = self._to_px(r, c)
            self.create_oval(x - 4, y - 4, x + 4, y + 4,
                             fill=LINE_COLOR, outline="", tags="grid")

        # 坐标标签 (A-T, skip I)
        col_labels = ([chr(ord('A') + i) for i in range(8)] +
                      [chr(ord('J') + i) for i in range(11)])
        for i, ch in enumerate(col_labels):
            x = MARGIN + i * CELL_SIZE
            self.create_text(x, 14, text=ch, fill=LINE_COLOR,
                             font=("Arial", 9), tags="grid")
            self.create_text(x, BOARD_PX - 14, text=ch, fill=LINE_COLOR,
                             font=("Arial", 9), tags="grid")
        for i in range(BOARD_SIZE):
            y = MARGIN + i * CELL_SIZE
            self.create_text(14, y, text=str(BOARD_SIZE - i), fill=LINE_COLOR,
                             font=("Arial", 9), tags="grid")
            self.create_text(BOARD_PX - 14, y, text=str(BOARD_SIZE - i), fill=LINE_COLOR,
                             font=("Arial", 9), tags="grid")

    # ──────────────────────────────────────────────
    #  绘制棋子 / 标记色块 / 悬停
    # ──────────────────────────────────────────────
    def draw_stones(self):
        self.delete("stone")
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self.game.board[r][c] != COLOR_EMPTY:
                    self._draw_stone(r, c, self.game.board[r][c])
        # 只在游戏进行中画悬停预览
        if not self.game.game_over:
            self._draw_hover()
        self.tag_raise("mark")

    def _draw_stone(self, r, c, color, ghost=False):
        x, y = self._to_px(r, c)
        outline = "#333333" if color == COLOR_BLACK else "#BBBBBB"
        fill_start = "#555555" if color == COLOR_BLACK else "#F5F5F5"
        fill_end = "#111111" if color == COLOR_BLACK else "#D0D0D0"

        if ghost:
            fill_start = "#BBBBBB" if color == COLOR_BLACK else "#F0F0F0"
            fill_end = "#999999" if color == COLOR_BLACK else "#E0E0E0"

        r2 = STONE_R - 1
        self.create_oval(x - r2, y - r2, x + r2, y + r2,
                         fill=fill_start, outline=outline, width=1,
                         tags="stone")
        self.create_oval(x - r2 + 5, y - r2 + 4,
                         x - r2 + 9, y - r2 + 8,
                         fill="#FFFFFF", outline="", tags="stone")

    def _draw_hover(self):
        self.delete("hover")
        if self.hover_pos and not self.game.game_over:
            r, c = self.hover_pos
            if self.game.board[r][c] == COLOR_EMPTY:
                self._draw_stone(r, c, self.game.current, ghost=True)
                self.lift("hover")

    def draw_marks(self):
        """绘制手动标记——中心小方块。
        黑=实心黑块，白=实心白块，中立=对角半黑半白。
        棋子与同色标记融为一体（黑子上黑块看不见）。"""
        self.delete("mark")
        side = STONE_R * 0.7
        half = side / 2
        for (r, c), owner in self.marks.items():
            x, y = self._to_px(r, c)
            if owner == COLOR_BLACK:
                self.create_rectangle(
                    x - half, y - half, x + half, y + half,
                    fill="#111111", outline="#444444", width=1, tags="mark")
            elif owner == COLOR_WHITE:
                self.create_rectangle(
                    x - half, y - half, x + half, y + half,
                    fill="#F0F0F0", outline="#BBBBBB", width=1, tags="mark")
            else:  # MARK_NEUTRAL — 对角半黑半白
                # 上半三角 = 黑，下半三角 = 白
                self.create_polygon(
                    x - half, y - half,  # 左上
                    x + half, y - half,  # 右上
                    x + half, y + half,  # 右下
                    fill="#111111", outline="", tags="mark")
                self.create_polygon(
                    x - half, y - half,  # 左上
                    x - half, y + half,  # 左下
                    x + half, y + half,  # 右下
                    fill="#F0F0F0", outline="", tags="mark")
                # 整体边框
                self.create_rectangle(
                    x - half, y - half, x + half, y + half,
                    fill="", outline="#666666", width=1, tags="mark")

    def refresh(self):
        self.draw_stones()
        self.draw_marks()

    # ──────────────────────────────────────────────
    #  鼠标事件
    # ──────────────────────────────────────────────
    def _click(self, event):
        pos = self._to_grid(event.x, event.y)
        if pos is not None:
            self.on_click(pos[0], pos[1])

    def _motion(self, event):
        pos = self._to_grid(event.x, event.y)
        if pos != self.hover_pos:
            self.hover_pos = pos
            self.draw_stones()

    def _leave(self, event):
        self.hover_pos = None
        self.draw_stones()
