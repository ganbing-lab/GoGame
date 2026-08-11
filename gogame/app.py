"""
围棋主窗口 — 布局面板、按钮、手动标记计分、所有 UI 逻辑。
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import os

import gogame.config as _cfg
from .config import (
    COLOR_BLACK, COLOR_WHITE, COLOR_EMPTY, MARK_NEUTRAL, KOMI,
    BOARD_SIZE, PANEL_W, WIN_W, WIN_H,
    PANEL_BG, BTN_BG, BG_COLOR, LINE_COLOR,
)
from .core import GoGame
from .board import BoardCanvas
from .board_config import BoardConfig, STANDARD_CONFIG
from .network import GoNetwork
from . import sgf


# 标记轮换顺序
MARK_CYCLE = [COLOR_WHITE, COLOR_BLACK, MARK_NEUTRAL]


class GoApp:
    """围棋主应用"""

    def __init__(self):
        self.game = GoGame(disabled=_cfg.DISABLED_CELLS)
        self.mode = "playing"      # "playing" | "scoring"
        self.view_pos = 0          # 当前查看的步数 (0 = 初始, len(moves) = 最新)
        self.board_config_path = None  # 当前棋盘配置文件路径（None=默认）
        self.net = None            # 联机连接
        self._my_color = None      # 联机时我的颜色 (COLOR_BLACK/COLOR_WHITE)
        self._network_poll_id = None  # after() id
        self._build_ui()

    # ──────────────────────────────────────────────
    #  UI 构建
    # ──────────────────────────────────────────────
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("围棋 Go Game")
        self.root.resizable(False, False)
        self.root.configure(bg=PANEL_BG)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.destroy())

        main_frame = tk.Frame(self.root, bg=PANEL_BG)
        main_frame.pack(padx=15, pady=15)

        self.canvas = BoardCanvas(main_frame, self.game, self._on_board_click)
        self.canvas.pack(side=tk.LEFT)

        # ── 可滚动右侧面板 ──
        panel_outer = tk.Frame(main_frame, width=PANEL_W + 16, bg=PANEL_BG)
        panel_outer.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        panel_outer.pack_propagate(False)

        panel_canvas = tk.Canvas(panel_outer, width=PANEL_W, bg=PANEL_BG,
                                 highlightthickness=0)
        self.scrollbar = tk.Scrollbar(panel_outer, orient=tk.VERTICAL,
                                      command=panel_canvas.yview)
        panel_canvas.configure(yscrollcommand=self.scrollbar.set)

        panel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._panel_canvas = panel_canvas

        panel = tk.Frame(panel_canvas, bg=PANEL_BG)
        self._panel = panel
        self._panel_win = panel_canvas.create_window((0, 0), window=panel,
                                                      anchor=tk.NW, width=PANEL_W)

        def _sync_panel_width(event):
            panel_canvas.itemconfig(self._panel_win, width=event.width)
        panel_canvas.bind("<Configure>", _sync_panel_width)

        def _on_mousewheel(event):
            panel_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        panel_canvas.bind("<Enter>", lambda e: panel_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        panel_canvas.bind("<Leave>", lambda e: panel_canvas.unbind_all("<MouseWheel>"))

        # ── 面板内容 ──
        self.turn_label = tk.Label(
            panel, text="", font=("Microsoft YaHei", 14, "bold"),
            bg=PANEL_BG, fg="#222222")
        self.turn_label.pack(pady=(10, 6))

        self.capture_label = tk.Label(
            panel, text="", font=("Consolas", 11),
            bg=PANEL_BG, fg="#444444", justify=tk.LEFT)
        self.capture_label.pack(pady=(0, 10))

        # 分数标签（数目模式显示）
        self.score_frame = tk.Frame(panel, bg=PANEL_BG)
        self.score_label = tk.Label(
            self.score_frame, text="", font=("Microsoft YaHei", 10),
            bg=PANEL_BG, fg="#444444", justify=tk.LEFT, wraplength=PANEL_W - 20)

        # 按钮样式
        btn = {"font": ("Microsoft YaHei", 11), "bg": BTN_BG,
               "activebackground": "#D5C9B0", "relief": tk.GROOVE,
               "bd": 2, "padx": 12, "pady": 4, "cursor": "hand2"}
        sep = {"font": ("Microsoft YaHei", 9), "bg": PANEL_BG, "fg": "#AAAAAA"}

        # 对局按钮
        self.pass_btn = tk.Button(panel, text="虚手 Pass", command=self._pass, **btn)
        self.pass_btn.pack(pady=3)
        self.end_btn = tk.Button(panel, text="终局 End Game", command=self._end_game, **btn)
        self.end_btn.pack(pady=3)
        self.resign_btn = tk.Button(panel, text="认输 Resign", command=self._resign, **btn)
        self.resign_btn.pack(pady=3)

        # 自定义棋盘按钮
        tk.Label(panel, text="── 棋盘 ──", **sep).pack(pady=(6, 2))
        self.load_board_btn = tk.Button(panel, text="加载棋盘文件", command=self._load_board, **btn)
        self.load_board_btn.pack(pady=2)
        self.board_name_label = tk.Label(
            panel, text="当前: 19路标准棋盘", font=("Microsoft YaHei", 8),
            bg=PANEL_BG, fg="#666666")
        self.board_name_label.pack(pady=(0, 0))

        # SGF 导入/导出按钮
        tk.Label(panel, text="── 棋谱 ──", **sep).pack(pady=(6, 2))
        self.export_sgf_btn = tk.Button(panel, text="导出 SGF", command=self._export_sgf, **btn)
        self.export_sgf_btn.pack(pady=2)
        self.import_sgf_btn = tk.Button(panel, text="导入 SGF", command=self._import_sgf, **btn)
        self.import_sgf_btn.pack(pady=2)

        # 翻棋导航栏
        nav_btn_style = {"font": ("Consolas", 12), "bg": BTN_BG,
                         "activebackground": "#D5C9B0", "relief": tk.GROOVE,
                         "bd": 2, "padx": 6, "pady": 2, "cursor": "hand2",
                         "width": 3}
        self.nav_frame = tk.Frame(panel, bg=PANEL_BG)
        self.nav_frame.pack(pady=(6, 2))
        self.prev_btn = tk.Button(self.nav_frame, text="◀", command=self._prev_move, **nav_btn_style)
        self.prev_btn.pack(side=tk.LEFT, padx=1)
        self.move_label = tk.Label(
            self.nav_frame, text="0 / 0", font=("Consolas", 11),
            bg=PANEL_BG, fg="#444444", width=10)
        self.move_label.pack(side=tk.LEFT, padx=4)
        self.next_btn = tk.Button(self.nav_frame, text="▶", command=self._next_move, **nav_btn_style)
        self.next_btn.pack(side=tk.LEFT, padx=1)

        # 数目模式按钮（默认隐藏）
        self.confirm_btn = tk.Button(panel, text="确认终局 Confirm",
                                     command=self._confirm_score, state=tk.DISABLED, **btn)
        self.cancel_score_btn = tk.Button(panel, text="返回下棋 Back",
                                          command=self._cancel_scoring, state=tk.DISABLED, **btn)

        self.new_btn = tk.Button(panel, text="新局 New Game", command=self._new_game, **btn)
        self.new_btn.pack(pady=(6, 8))

        # ── 联机按钮 ──
        tk.Label(panel, text="── 联机 ──", **sep).pack(pady=(6, 2))
        self.host_btn = tk.Button(panel, text="创建对局 (主机)", command=self._host_game, **btn)
        self.host_btn.pack(pady=2)
        self.join_btn = tk.Button(panel, text="加入对局 (客机)", command=self._join_game, **btn)
        self.join_btn.pack(pady=2)
        self.disconnect_btn = tk.Button(panel, text="断开连接", command=self._disconnect,
                                       state=tk.DISABLED, **btn)
        self.disconnect_btn.pack(pady=2)
        self.net_status_label = tk.Label(
            panel, text="", font=("Microsoft YaHei", 8),
            bg=PANEL_BG, fg="#666666")
        self.net_status_label.pack(pady=(0, 0))

        self.hint_label = tk.Label(
            panel, text="", font=("Microsoft YaHei", 9),
            bg=PANEL_BG, fg="#888888", wraplength=PANEL_W - 20, justify=tk.LEFT)
        self.hint_label.pack(pady=(0, 8))

        self._after_scroll_update()

        self._update_panel()
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - WIN_W) // 2
        y = (self.root.winfo_screenheight() - WIN_H) // 2
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

    # ──────────────────────────────────────────────
    #  面板刷新
    # ──────────────────────────────────────────────
    def _after_scroll_update(self):
        self._panel.update_idletasks()
        panel_h = self._panel.winfo_reqheight()
        canvas_h = self._panel_canvas.winfo_height()
        self._panel_canvas.configure(scrollregion=(0, 0, PANEL_W, panel_h))
        if panel_h > canvas_h:
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.scrollbar.pack_forget()

    def _update_panel(self):
        g = self.game
        if g.game_over and self.mode != "scoring":
            if g.winner is not None:
                wname = "黑方" if g.winner == COLOR_BLACK else "白方"
                self.turn_label.config(text=f"{wname}\n认输胜")
            else:
                self.turn_label.config(text="对局结束")
        else:
            name = "⚫ 黑方" if g.current == COLOR_BLACK else "⚪ 白方"
            self.turn_label.config(text=f"{name}\n落子")

        self.capture_label.config(
            text=f"提子 ⚫ {g.captured[COLOR_BLACK]}  |  ⚪ {g.captured[COLOR_WHITE]}")

    def _show_score(self):
        b, w = GoGame.score_from_marks(self.canvas.marks)
        white_with_komi = w + KOMI / 2
        diff = b - white_with_komi
        if diff > 0:
            wname = "黑方"
            result = f"{diff:.1f} 子"
        else:
            wname = "白方"
            result = f"{-diff:.1f} 子"

        # 统计各类标记数量
        n_black = sum(1 for v in self.canvas.marks.values() if v == COLOR_BLACK)
        n_white = sum(1 for v in self.canvas.marks.values() if v == COLOR_WHITE)
        n_neutral = sum(1 for v in self.canvas.marks.values() if v == MARK_NEUTRAL)

        self.score_label.config(
            text=(f"【手动标记计分】\n"
                  f"  ⚫ 黑方: {b:.1f} 子\n"
                  f"  ⚪ 白方: {w:.1f} 子\n"
                  f"  贴子:     ⚪ +{KOMI/2:.2f}\n"
                  f"  ───────\n"
                  f"  白方贴子后: {white_with_komi:.1f}\n"
                  f"  差: {wname}胜 {result}\n"
                  f"\n"
                  f"标记统计:\n"
                  f"  ⚫ {n_black}  ⚪ {n_white}  ⬜ {n_neutral}\n"
                  f"\n"
                  f"棋盘总计: {len(self.canvas.marks)} 点已标记"),
            justify=tk.LEFT)

    # ──────────────────────────────────────────────
    #  标记连通区域轮换
    # ──────────────────────────────────────────────
    def _connected_region(self, r, c):
        """找到 (r,c) 所在连通区域的坐标集。
        连通判定：用当前棋盘 colour（空点是 COLOR_EMPTY，子点是其颜色），
        不是 marks 里的 owner。这样：
        - 空的区域 → 一组连通空地
        - 棋子及其连通同色子 → 一组连通子"""
        color = self.game.board[r][c]
        # 用了 _group 来遍历所有同色连通格子
        return self.game._group(r, c)

    def _cycle_mark(self, r, c):
        """将 (r,c) 所在连通区域的所有点的标记轮换一次."""
        region = self.game.mark_region_at(r, c)
        if not region:
            return

        # 取当前任意一点的 mark，拿下一个轮换值
        first = next(iter(region))
        current_mark = self.canvas.marks.get(first, MARK_NEUTRAL)
        try:
            idx = MARK_CYCLE.index(current_mark)
        except ValueError:
            idx = 0
        next_mark = MARK_CYCLE[(idx + 1) % len(MARK_CYCLE)]

        for pt in region:
            self.canvas.marks[pt] = next_mark

    # ──────────────────────────────────────────────
    #  棋盘点击分发
    # ──────────────────────────────────────────────
    def _on_board_click(self, r, c):
        # 联机模式下，只有轮到自己才能落子
        if self._my_color is not None and self.game.current != self._my_color:
            self.hint_label.config(text="等待对手落子...")
            self.root.after(1200, lambda: self.hint_label.config(text=""))
            return
        if self.mode == "scoring":
            self._cycle_mark(r, c)
            self.canvas.refresh()
            self._show_score()
        elif self.mode == "playing" and not self.game.game_over:
            self._play_move(r, c)

    def _play_move(self, r, c):
        if self.view_pos < len(self.game.moves):
            self.view_pos = len(self.game.moves)
            self.game.set_position(self.view_pos)
        taken = self.game.play(r, c)
        if taken == -1:
            self.hint_label.config(text="此处不能落子！")
            self.root.after(1200, lambda: self.hint_label.config(text=""))
            return
        self.view_pos = len(self.game.moves)
        self.hint_label.config(text=f"提{taken}子！" if taken else "")
        if taken:
            self.root.after(1500, lambda: self.hint_label.config(text=""))
        self.canvas.refresh()
        self._update_panel()
        self._update_nav()
        # 联机：发送落子给对方
        if self.net and self.net.is_connected():
            self.net.send({"type": "move", "r": r, "c": c})

    # ──────────────────────────────────────────────
    #  对局按钮
    # ──────────────────────────────────────────────
    def _pass(self):
        if self.game.game_over or self.mode == "scoring":
            return
        # 联机模式，只有轮到自己才能虚手
        if self._my_color is not None and self.game.current != self._my_color:
            self.hint_label.config(text="等待对手操作...")
            self.root.after(1200, lambda: self.hint_label.config(text=""))
            return
        ended = self.game.pass_move()
        if ended:
            self._enter_scoring()
        else:
            self.canvas.refresh()
            self._update_panel()
        self.view_pos = len(self.game.moves)
        self._update_nav()
        if self.net and self.net.is_connected():
            self.net.send({"type": "pass"})

    def _end_game(self):
        if self.game.game_over or self.mode == "scoring":
            return
        if messagebox.askyesno("终局", "确定要终局吗？\n将进入标记计分阶段。"):
            self.game.game_over = True
            self._enter_scoring()

    def _resign(self):
        if self.game.game_over or self.mode == "scoring":
            return
        # 联机模式，只有轮到自己才能认输
        if self._my_color is not None and self.game.current != self._my_color:
            self.hint_label.config(text="等待对手操作...")
            self.root.after(1200, lambda: self.hint_label.config(text=""))
            return
        name = "黑方" if self.game.current == COLOR_BLACK else "白方"
        if messagebox.askyesno("认输", f"{name}确定认输吗？"):
            self.game.resign()
            self.canvas.refresh()
            self._update_panel()
            self._disable_play_buttons()
            if self.net and self.net.is_connected():
                self.net.send({"type": "resign"})

    # ──────────────────────────────────────────────
    #  标记计分模式
    # ──────────────────────────────────────────────
    def _init_marks(self):
        """初始标记：棋盘上每格赋初值。
        空点 = 中立（中性），黑子 = 黑，白子 = 白。
        跳过禁用格。"""
        self.canvas.marks = {}
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if (r, c) in _cfg.DISABLED_CELLS:
                    continue
                cell = self.game.board[r][c]
                if cell == COLOR_EMPTY:
                    self.canvas.marks[(r, c)] = MARK_NEUTRAL
                elif cell == COLOR_BLACK:
                    self.canvas.marks[(r, c)] = COLOR_BLACK
                elif cell == COLOR_WHITE:
                    self.canvas.marks[(r, c)] = COLOR_WHITE

    def _enter_scoring(self):
        self.mode = "scoring"
        self._init_marks()
        self.canvas.refresh()
        self._update_panel()

        # 隐藏对局按钮
        self.pass_btn.config(state=tk.DISABLED)
        self.end_btn.config(state=tk.DISABLED)
        self.resign_btn.config(state=tk.DISABLED)
        self.pass_btn.pack_forget()
        self.end_btn.pack_forget()
        self.resign_btn.pack_forget()

        # 显示分数面板
        self.score_frame.pack(pady=(5, 0), before=self.new_btn)
        self.score_label.pack()
        for b in (self.confirm_btn, self.cancel_score_btn):
            b.pack(pady=3, before=self.new_btn)
            b.config(state=tk.NORMAL)

        self.turn_label.config(text="标记阶段\n点击棋盘标记归属\n⚪ → ⚫ → ⬜ → ⚪ …")
        self._show_score()
        self._after_scroll_update()

        # 禁用翻棋导航
        self.prev_btn.config(state=tk.DISABLED)
        self.next_btn.config(state=tk.DISABLED)

    def _confirm_score(self):
        if not messagebox.askyesno("确认终局", "确认当前结果为最终结果吗？"):
            return
        b, w = GoGame.score_from_marks(self.canvas.marks)
        wc = w + KOMI / 2
        wname, diff = ("黑方", b - wc) if b > wc else ("白方", wc - b)
        self.turn_label.config(text=f"{wname} 胜\n{diff:.1f} 子")
        self._disable_scoring_buttons()
        self.canvas.config(cursor="hand2")

    def _cancel_scoring(self):
        self.mode = "playing"
        self.game.game_over = False
        self.canvas.marks = {}
        self.canvas.refresh()

        self.score_frame.pack_forget()
        for b in (self.confirm_btn, self.cancel_score_btn):
            b.pack_forget()

        for b in (self.pass_btn, self.end_btn, self.resign_btn):
            b.pack(pady=4)
            b.config(state=tk.NORMAL)
        self.canvas.config(cursor="hand2")
        self._update_panel()
        self._update_nav()
        self._after_scroll_update()

    def _disable_play_buttons(self):
        for b in (self.pass_btn, self.end_btn, self.resign_btn):
            b.config(state=tk.DISABLED)

    def _disable_scoring_buttons(self):
        for b in (self.confirm_btn, self.cancel_score_btn):
            b.config(state=tk.DISABLED)

    def _new_game(self):
        if not messagebox.askyesno("新局", "确定开始新的一局吗？"):
            return

        if self.mode == "scoring":
            self.score_frame.pack_forget()
            for b in (self.confirm_btn, self.cancel_score_btn):
                b.pack_forget()
            for b in (self.pass_btn, self.end_btn, self.resign_btn):
                b.pack(pady=4)
                b.config(state=tk.NORMAL)

        self.mode = "playing"
        self.game.reset()
        self.view_pos = 0
        self.canvas.marks = {}
        self.canvas.hover_pos = None
        self.canvas.refresh()
        self.canvas.config(cursor="hand2")
        self.hint_label.config(text="")
        self._update_panel()
        self._update_nav()
        self._after_scroll_update()

    # ──────────────────────────────────────────────
    #  联机对战
    # ──────────────────────────────────────────────
    def _host_game(self):
        """创建主机，监听端口等客机连接。"""
        if self.net and self.net.is_connected():
            messagebox.showinfo("联机", "已处于联机状态，请先断开。")
            return

        from tkinter import simpledialog
        port_str = simpledialog.askstring(
            "创建对局", "请输入监听端口:",
            parent=self.root)
        if not port_str:
            return
        try:
            port = int(port_str.strip())
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字。")
            return

        if self.game.moves:
            if not messagebox.askyesno("创建对局", "当前对局将被清除，确定继续？"):
                return

        self.net = GoNetwork(
            on_message=self._on_network_message,
            on_disconnect=self._on_network_disconnect,
            on_connected=self._on_network_connected)

        self._my_color = COLOR_BLACK  # 主机执黑
        self._reset_with_current_board()
        self._disable_connect_buttons()

        self.net.start_server(port, name="主机")
        self.net_status_label.config(text=f"等待连接... 端口 {port}")
        self._start_poll()

    def _join_game(self):
        """加入对局，连接主机。"""
        if self.net and self.net.is_connected():
            messagebox.showinfo("联机", "已处于联机状态，请先断开。")
            return

        from tkinter import simpledialog
        addr = simpledialog.askstring(
            "加入对局", "请输入主机地址 (如 192.168.1.1:9000 或 [::1]:9000):",
            parent=self.root)
        if not addr:
            return

        # 解析 host:port，处理 IPv6 的 [addr]:port
        host = addr.strip()
        port = 9000
        if host.startswith("[") and "]" in host:
            bracket_end = host.index("]")
            ip = host[1:bracket_end]
            rest = host[bracket_end + 1:]
            host = ip
            if rest.startswith(":"):
                port = int(rest[1:])
        elif ":" in host:
            last_colon = host.rfind(":")
            try:
                port = int(host[last_colon + 1:])
                host = host[:last_colon]
            except ValueError:
                pass  # 可能是纯 IPv6 地址没有端口，用默认

        if self.game.moves:
            if not messagebox.askyesno("加入对局", "当前对局将被清除，确定继续？"):
                return

        self.net = GoNetwork(
            on_message=self._on_network_message,
            on_disconnect=self._on_network_disconnect,
            on_connected=self._on_network_connected)

        self._my_color = COLOR_WHITE  # 客机执白
        self._reset_with_current_board()
        self._disable_connect_buttons()

        self.net.connect_to(host, port, name="客机")
        self.net_status_label.config(text=f"正在连接 {addr}...")
        self._start_poll()

    def _disconnect(self):
        """主动断开联机。"""
        if self.net:
            self.net.disconnect()
            self.net = None
        self._my_color = None
        self._stop_poll()
        self.net_status_label.config(text="已断开")
        self.host_btn.config(state=tk.NORMAL)
        self.join_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        self.hint_label.config(text="")

    def _disable_connect_buttons(self):
        self.host_btn.config(state=tk.DISABLED)
        self.join_btn.config(state=tk.DISABLED)
        self.disconnect_btn.config(state=tk.NORMAL)

    def _start_poll(self):
        """启动网络轮询（每 100ms 检查收信）。"""
        if self._network_poll_id is not None:
            return
        def _poll():
            if self.net:
                self.net.poll()
            if self.net:
                self._network_poll_id = self.root.after(100, _poll)
            else:
                self._network_poll_id = None
        self._network_poll_id = self.root.after(100, _poll)

    def _stop_poll(self):
        if self._network_poll_id is not None:
            self.root.after_cancel(self._network_poll_id)
            self._network_poll_id = None

    def _on_network_connected(self, peer):
        """连接建立后的回调。"""
        def _connected():
            color_name = "⚫ 黑方" if self._my_color == COLOR_BLACK else "⚪ 白方"
            self.net_status_label.config(text=f"已连接 ({color_name})")
            self._update_panel()
        self.root.after(0, _connected)

    def _on_network_disconnect(self, peer):
        """对方断开连接的回调。"""
        def _dc():
            name = "对手断开连接"
            if peer is None:
                name = "连接失败"
            self.net_status_label.config(text=name)
            self.host_btn.config(state=tk.NORMAL)
            self.join_btn.config(state=tk.NORMAL)
            self.disconnect_btn.config(state=tk.DISABLED)
            if self.net:
                self.net.disconnect()
                self.net = None
            self._my_color = None
            self._stop_poll()
            self._update_panel()
        self.root.after(0, _dc)

    def _on_network_message(self, peer, msg):
        """收到对手消息的回调。"""
        msg_type = msg.get("type", "")

        if msg_type == "hello":
            # 客机收到主机的 hello，同步棋盘配置
            if self._my_color == COLOR_WHITE and "disabled" in msg:
                disabled_list = msg.get("disabled", [])
                _cfg.DISABLED_CELLS = set(tuple(d) for d in disabled_list)
                self._reset_with_current_board()
                self.canvas._draw_board()
                self.canvas.refresh()
            return

        if self.mode != "playing" or self.game.game_over:
            return

        if msg_type == "move":
            r, c = msg["r"], msg["c"]
            self.game.play(r, c)
            self.view_pos = len(self.game.moves)
            self.canvas.refresh()
            self._update_panel()
            self._update_nav()

        elif msg_type == "pass":
            ended = self.game.pass_move()
            if ended:
                self._enter_scoring()
            else:
                self.canvas.refresh()
                self._update_panel()
            self.view_pos = len(self.game.moves)
            self._update_nav()

        elif msg_type == "resign":
            self.game.resign()
            self.canvas.refresh()
            self._update_panel()
            self._disable_play_buttons()

    # ──────────────────────────────────────────────
    #  自定义棋盘加载
    # ──────────────────────────────────────────────
    def _load_board(self):
        """加载自定义棋盘文件。非标准棋盘禁用 SGF 导入。"""
        if self.game.moves:
            if not messagebox.askyesno(
                "加载棋盘", "当前对局有棋谱记录，加载新棋盘将清除对局。\n确定继续吗？"
            ):
                return

        board_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "boards")
        if not os.path.isdir(board_dir):
            board_dir = os.path.dirname(os.path.dirname(__file__))

        path = filedialog.askopenfilename(
            title="加载棋盘配置文件",
            initialdir=board_dir,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return

        try:
            cfg = BoardConfig.load(path)
            if cfg.size != BOARD_SIZE:
                messagebox.showerror(
                    "棋盘尺寸不匹配",
                    f"棋盘文件定义尺寸为 {cfg.size}，当前程序只支持 {BOARD_SIZE} 路棋盘。\n"
                    f"请使用 {BOARD_SIZE} 路的棋盘文件。")
                return

            _cfg.DISABLED_CELLS = cfg.disabled
            _cfg.BOARD_CONFIG_NAME = cfg.name
            _cfg.BOARD_IS_CUSTOM = not cfg.is_standard
            self.board_config_path = path

            self.board_name_label.config(text=f"当前: {cfg.name}")

            if cfg.is_standard:
                self.import_sgf_btn.config(state=tk.NORMAL, text="导入 SGF")
            else:
                self.import_sgf_btn.config(state=tk.DISABLED,
                    text="导入 SGF (自定义棋盘不可用)")

            self._reset_with_current_board()
            self.canvas._draw_board()
            self.canvas.refresh()

            msg = f"已加载棋盘: {cfg.name}"
            if cfg.disabled:
                msg += f"\n禁用格数: {len(cfg.disabled)}"
            messagebox.showinfo("加载成功", msg)

        except Exception as e:
            messagebox.showerror("加载失败", f"无法加载棋盘文件:\n{e}")

    def _reset_with_current_board(self):
        """使用全局 config 中的当前 DISABLED_CELLS 重建游戏。"""
        # 清理计分模式 UI
        if self.mode == "scoring":
            self.score_frame.pack_forget()
            for b in (self.confirm_btn, self.cancel_score_btn):
                b.pack_forget()
            for b in (self.pass_btn, self.end_btn, self.resign_btn):
                b.pack(pady=4)
                b.config(state=tk.NORMAL)

        self.game = GoGame(disabled=_cfg.DISABLED_CELLS)
        self.mode = "playing"
        self.view_pos = 0
        self.canvas.marks = {}
        self.canvas.hover_pos = None
        self.canvas.game = self.game
        self.canvas.config(cursor="hand2")
        self.hint_label.config(text="")
        self._update_panel()
        self._update_nav()
        self._after_scroll_update()

    # ──────────────────────────────────────────────
    #  翻棋导航
    # ──────────────────────────────────────────────
    def _update_nav(self):
        total = len(self.game.moves)
        self.move_label.config(text=f"{self.view_pos} / {total}")
        self.prev_btn.config(state=tk.NORMAL if self.view_pos > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.view_pos < total else tk.DISABLED)

    def _prev_move(self):
        if self.view_pos <= 0:
            return
        self.view_pos -= 1
        self.game.set_position(self.view_pos)
        self.canvas.refresh()
        self._update_panel()
        self._update_nav()

    def _next_move(self):
        if self.view_pos >= len(self.game.moves):
            return
        self.view_pos += 1
        self.game.set_position(self.view_pos)
        self.canvas.refresh()
        self._update_panel()
        self._update_nav()

    # ──────────────────────────────────────────────
    #  SGF 导入/导出
    # ──────────────────────────────────────────────
    def _export_sgf(self):
        if not self.game.moves and all(
            self.game.board[r][c] == COLOR_EMPTY
            for r in range(BOARD_SIZE) for c in range(BOARD_SIZE)
        ):
            messagebox.showwarning("无棋谱", "棋盘为空，没有棋谱可导出。")
            return

        path = filedialog.asksaveasfilename(
            title="导出 SGF 棋谱",
            defaultextension=".sgf",
            filetypes=[("SGF 文件", "*.sgf"), ("所有文件", "*.*")],
            initialfile="gogame.sgf",
        )
        if not path:
            return

        try:
            result = None
            if self.game.game_over:
                if self.game.winner is not None:
                    wn = "B" if self.game.winner == COLOR_BLACK else "W"
                    result = f"{wn}+Resign"
                elif self.mode == "scoring":
                    b, w = GoGame.score_from_marks(self.canvas.marks)
                    wc = w + KOMI / 2
                    if b > wc:
                        result = f"B+{b - wc:.1f}"
                    else:
                        result = f"W+{wc - b:.1f}"

            name = os.path.splitext(os.path.basename(path))[0]
            content = sgf.game_to_sgf(self.game, game_result=result, game_name=name)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            n_moves = len(self.game.moves)
            messagebox.showinfo("导出成功", f"已导出 {n_moves} 手棋谱到:\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _import_sgf(self):
        if self.game.moves and not messagebox.askyesno(
            "导入棋谱", "当前对局有棋谱记录，导入将覆盖当前对局。\n确定继续吗？"
        ):
            return

        path = filedialog.askopenfilename(
            title="导入 SGF 棋谱",
            filetypes=[("SGF 文件", "*.sgf"), ("所有文件", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            messagebox.showerror("读取失败", f"无法读取文件:\n{e}")
            return

        try:
            if self.mode == "scoring":
                self._cancel_scoring()
            else:
                self.mode = "playing"
                self.game.reset()
                self.view_pos = 0
                self.canvas.marks = {}
                self.canvas.hover_pos = None

            info = sgf.sgf_to_game(self.game, text)
            self.view_pos = len(self.game.moves)
            self.canvas.refresh()
            self._update_panel()
            self._update_nav()
            self.hint_label.config(text="")

            msg = f"成功加载 {info['moves_loaded']} 手棋谱"
            if info.get("handicap"):
                msg += f"\n让子: {info['handicap']} 子"
            if info.get("komi") and info["komi"] != KOMI:
                msg += f"\n贴目: {info['komi']}（本应用默认 {KOMI}）"
            if info.get("result"):
                msg += f"\n结果: {info['result']}"
            if info.get("invalid_moves"):
                msg += f"\n⚠ {len(info['invalid_moves'])} 手无法执行，已跳过"
            messagebox.showinfo("导入成功", msg)

        except ValueError as e:
            messagebox.showerror("导入失败", str(e))
        except Exception as e:
            messagebox.showerror("导入失败", f"解析棋谱时出错:\n{e}")

    def run(self):
        self.root.mainloop()
