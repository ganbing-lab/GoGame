"""
围棋常量配置：棋盘尺寸、颜色、视觉参数。
"""

BOARD_SIZE = 19
CELL_SIZE = 36
MARGIN = 44
STONE_R = int(CELL_SIZE * 0.44)
PANEL_W = 200
KOMI = 6.5
BOARD_PX = MARGIN * 2 + CELL_SIZE * (BOARD_SIZE - 1)
WIN_W = BOARD_PX + PANEL_W + 60
WIN_H = BOARD_PX + 160

# 自定义棋盘配置：从 boards/ 目录加载
# 默认标准 19 路棋盘，无禁用格
DISABLED_CELLS = set()       # set of (row, col)
BOARD_CONFIG_NAME = "19路标准棋盘"
BOARD_IS_CUSTOM = False      # 是否加载了非标准棋盘

# 棋子颜色常量（无 UI 依赖，纯逻辑层可用）
COLOR_EMPTY = 0
COLOR_BLACK = 1
COLOR_WHITE = 2

# 手动标记阶段用：半黑半白（中立）
MARK_NEUTRAL = 3

# UI 颜色
BG_COLOR = "#DEB887"       # 木色棋盘
LINE_COLOR = "#4A3728"     # 深色棋盘线
PANEL_BG = "#F0EAD6"      # 面板底色
BTN_BG = "#E8DCC8"        # 按钮底色

# 星位
STAR_POINTS = [
    (3, 3), (3, 9), (3, 15),
    (9, 3), (9, 9), (9, 15),
    (15, 3), (15, 9), (15, 15),
]
