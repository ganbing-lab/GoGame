"""
SGF (Smart Game Format) FF[4] 棋谱导入/导出。
支持基本属性（SZ, KM, HA, RE, B, W, AB, AW, C）和多分支。
"""

import re
from datetime import datetime
from .config import BOARD_SIZE, COLOR_BLACK, COLOR_WHITE, COLOR_EMPTY, KOMI


# ──────────────────────────────────────────────────────────
#  坐标转换
# ──────────────────────────────────────────────────────────
_COL_LETTERS = "abcdefghijklmnopqrs"  # 19 路

# SGF 坐标 → (row, col)，row 从 0 起（上边为 0）
def _sgf_to_rc(sgf_coord):
    """aa → (0, 0), ss → (18, 18)。返回 None 若是 '' 或 'tt' (pass)。"""
    if not sgf_coord or sgf_coord == "tt":
        return None
    c = _COL_LETTERS.find(sgf_coord[0])
    r = _COL_LETTERS.find(sgf_coord[1])
    if c == -1 or r == -1:
        return None
    return r, c

def _rc_to_sgf(r, c):
    """(0, 0) → 'aa', (18, 18) → 'ss'。pass 返回 'tt'。"""
    if r == -1:
        return "tt"
    return _COL_LETTERS[c] + _COL_LETTERS[r]


# ──────────────────────────────────────────────────────────
#  SGF 分词器
# ──────────────────────────────────────────────────────────
def _tokenize(text):
    """将 SGF 文本分解为 token 流：(type, value)。"""
    tokens = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(" or ch == ")" or ch == ";" or ch == "]":
            tokens.append(("punct", ch))
            i += 1
        elif ch.isalpha() and ch.isupper():
            j = i + 1
            while j < n and text[j].isalpha() and text[j].isupper():
                j += 1
            tokens.append(("prop", text[i:j]))
            i = j
        elif ch == "[":
            tokens.append(("punct", "["))
            j = i + 1
            buf = []
            depth = 1           # 支持值内嵌套 [...]（如 DT[20250219[15:00]]）
            while j < n and depth > 0:
                if text[j] == "[":
                    depth += 1
                    buf.append(text[j])
                elif text[j] == "]":
                    depth -= 1
                    if depth > 0:
                        buf.append(text[j])
                elif text[j] == "\\" and j + 1 < n:
                    j += 1
                    buf.append(text[j])
                else:
                    buf.append(text[j])
                j += 1
            if depth == 0:
                tokens.append(("value", "".join(buf)))
                tokens.append(("punct", "]"))
                i = j
            else:
                i = j
        else:
            i += 1
    return tokens


# ──────────────────────────────────────────────────────────
#  SGF 解析器 —— 递归下降
# ──────────────────────────────────────────────────────────
def _parse_collection(tokens, pos):
    """解析根级 GameTree 集合。返回 (game_trees, new_pos)。"""
    trees = []
    while pos < len(tokens) and tokens[pos] == ("punct", "("):
        tree, pos = _parse_tree(tokens, pos)
        trees.append(tree)
    return trees, pos


def _parse_tree(tokens, pos):
    """解析一个 GameTree = '(' Sequence {GameTree} ')'。"""
    assert pos < len(tokens) and tokens[pos] == ("punct", "(")
    pos += 1  # 跳过 '('
    nodes, pos = _parse_sequence(tokens, pos)
    children = []
    while pos < len(tokens) and tokens[pos] == ("punct", "("):
        child, pos = _parse_tree(tokens, pos)
        children.append(child)
    assert pos < len(tokens) and tokens[pos] == ("punct", ")"), \
        f"Expected ')' at pos {pos}, got {tokens[pos]}"
    pos += 1  # 跳过 ')'
    return {"nodes": nodes, "children": children}, pos


def _parse_sequence(tokens, pos):
    """解析一个 Sequence = Node {Node}。Node 以 ';' 开头。"""
    nodes = []
    while pos < len(tokens) and tokens[pos] == ("punct", ";"):
        node, pos = _parse_node(tokens, pos + 1)
        nodes.append(node)
    return nodes, pos


def _parse_node(tokens, pos):
    """解析一个 Node = {PropIdent PropValue {PropValue}}。"""
    node = {}
    while pos < len(tokens):
        kind, val = tokens[pos]
        if kind != "prop":
            break
        prop = val
        pos += 1
        values = []
        while pos < len(tokens) and tokens[pos] == ("punct", "["):
            pos += 1  # 跳过 '['
            assert pos < len(tokens) and tokens[pos][0] == "value", \
                f"Expected value after '[', got {tokens[pos]} at pos {pos}"
            values.append(tokens[pos][1])
            pos += 1  # 跳过 value
            assert pos < len(tokens) and tokens[pos] == ("punct", "]"), \
                f"Expected ']' at pos {pos}"
            pos += 1  # 跳过 ']'
        node[prop] = values
    return node, pos


# ──────────────────────────────────────────────────────────
#  扁平化 GameTree → move list
# ──────────────────────────────────────────────────────────
def _flatten_tree(tree):
    """将(主分支)GameTree 扁平化为 (init_nodes, moves, result) 三元组。
       moves 格式：[(r, c, color), ...]，pass 为 (-1, -1, color)。
    """
    nodes = tree.get("nodes", [])
    if not nodes:
        return [], [], None

    # 第一个 node 是根节点，包含游戏属性和初始设置
    root = nodes[0]
    moves = []

    # 解析棋盘尺寸
    sz = int(root.get("SZ", [str(BOARD_SIZE)])[0]) if "SZ" in root else BOARD_SIZE

    turn = COLOR_BLACK
    for node in nodes[1:]:
        if "B" in node:
            rc = _sgf_to_rc(node["B"][0])
            if rc is None:   # pass
                moves.append((-1, -1, COLOR_BLACK))
            else:
                moves.append((*rc, COLOR_BLACK))
            turn = COLOR_WHITE
        elif "W" in node:
            rc = _sgf_to_rc(node["W"][0])
            if rc is None:
                moves.append((-1, -1, COLOR_WHITE))
            else:
                moves.append((*rc, COLOR_WHITE))
            turn = COLOR_BLACK

    result = root.get("RE", [None])[0]
    return root, nodes, sz, moves, result


# ──────────────────────────────────────────────────────────
#  SGF 读写接口
# ──────────────────────────────────────────────────────────
def load_sgf(text):
    """解析 SGF 文本，返回 parsed 结构。

    返回格式：
        {
            "board_size": int,
            "komi": float,
            "handicap": int,
            "moves": [(r, c, color), ...],     # pass 为 (-1, -1, color)
            "root_props": {prop: [values], ...}, # 根节点属性
            "result": str or None,
            "ab": [(r, c), ...],   # 预设黑子
            "aw": [(r, c), ...],   # 预设白子
        }
    """
    tokens = _tokenize(text)
    trees, _ = _parse_collection(tokens, 0)
    if not trees:
        raise ValueError("Empty or invalid SGF file")

    # 只取主分支（第一个 GameTree）
    root, nodes, sz, moves, result = _flatten_tree(trees[0])

    km = float(root.get("KM", [str(KOMI)])[0]) if "KM" in root else KOMI
    ha = int(root.get("HA", ["0"])[0]) if "HA" in root else 0

    ab = []
    aw = []
    if "AB" in root:
        for v in root["AB"]:
            rc = _sgf_to_rc(v)
            if rc:
                ab.append(rc)
    if "AW" in root:
        for v in root["AW"]:
            rc = _sgf_to_rc(v)
            if rc:
                aw.append(rc)

    # handicap 也可从 AB 数量推断
    if ha == 0 and ab:
        ha = len(ab)

    return {
        "board_size": sz,
        "komi": km,
        "handicap": ha,
        "moves": moves,
        "root_props": root,
        "result": result,
        "ab": ab,
        "aw": aw,
    }


def dump_sgf(game_result=None, winner=None, komi=KOMI, board_size=BOARD_SIZE,
             moves=None, ab=None, aw=None, game_name=None, comment=None):
    """将游戏导出为 SGF 文本。

    参数：
        game_result: str "B+R" / "W+3.5" / "B+Resign" 等
        winner: COLOR_BLACK/COLOR_WHITE/None
        moves: [(r, c, color), ...]  pass 为 (-1, -1, color)
        ab: [(r, c), ...] 预设黑子
        aw: [(r, c), ...] 预设白子
    """
    if moves is None:
        moves = []

    lines = ["(;"]
    lines.append(f"SZ[{board_size}]")
    lines.append(f"KM[{komi}]")

    if game_name:
        lines.append(f"GN[{_escape(game_name)}]")

    if ab:
        ab_str = "".join(f"[{_rc_to_sgf(r, c)}]" for r, c in ab)
        lines.append(f"AB{ab_str}")
    if aw:
        aw_str = "".join(f"[{_rc_to_sgf(r, c)}]" for r, c in aw)
        lines.append(f"AW{aw_str}")

    lines.append(f"HA[{len(ab) if ab else 0}]")

    if game_result:
        lines.append(f"RE[{game_result}]")

    if comment:
        lines.append(f"C[{_escape(comment)}]")

    date_str = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"DT[{date_str}]")

    # 走子序列
    for r, c, color in moves:
        tag = "B" if color == COLOR_BLACK else "W"
        lines.append(f";{tag}[{_rc_to_sgf(r, c)}]")

    lines.append(")")
    return "\n".join(lines)


def _escape(text):
    """转义 SGF 文本值中的特殊字符。"""
    return text.replace("\\", "\\\\").replace("]", "\\]")


# ──────────────────────────────────────────────────────────
#  便捷接口：直接与 GoGame 交互
# ──────────────────────────────────────────────────────────
def game_to_sgf(game, game_result=None, game_name=None):
    """从 GoGame 对象导出 SGF 文本。"""
    ab, aw = [], []

    # 初始局面（如果有预设子）
    # 从 moves 和当前 board 反推
    # 简化：直接导出行棋序列

    result = game_result
    if result is None and game.game_over:
        if game.winner is not None:
            wn = "B" if game.winner == COLOR_BLACK else "W"
            result = f"{wn}+Resign"
        else:
            # 使用日式计分
            b, w, _ = game.score_japanese()
            if b > w:
                result = f"B+{b - w:.1f}"
            else:
                result = f"W+{w - b:.1f}"

    return dump_sgf(
        game_result=result,
        komi=KOMI,
        board_size=BOARD_SIZE,
        moves=game.moves,
        ab=ab,
        aw=aw,
        game_name=game_name,
    )


def sgf_to_game(game, sgf_text):
    """将 SGF 文本加载到 GoGame 对象。

    重置 board，回放所有走子。返回加载信息 dict。
    """
    parsed = load_sgf(sgf_text)
    game.reset()

    # 如果棋盘尺寸不匹配，仅支持 19路
    if parsed["board_size"] != BOARD_SIZE:
        raise ValueError(f"只支持 {BOARD_SIZE} 路棋盘，SGF 为 {parsed['board_size']} 路")

    # 放置预设子（AB / AW）
    for r, c in parsed["ab"]:
        game.board[r][c] = COLOR_BLACK
    for r, c in parsed["aw"]:
        game.board[r][c] = COLOR_WHITE

    # 回放走子
    invalid = []
    for i, (r, c, color) in enumerate(parsed["moves"]):
        if r == -1:  # pass
            game.pass_move()
        else:
            # 如果颜色不对齐（先有 AB 等），跳过
            if game.current != color:
                invalid.append((i, r, c, color, "turn_mismatch"))
                continue
            taken = game.play(r, c)
            if taken == -1:
                invalid.append((i, r, c, color, "illegal"))
                # 尝试恢复：重新设置当前颜色再继续
                game.current = color

    return {
        "moves_loaded": len(parsed["moves"]),
        "invalid_moves": invalid,
        "board_size": parsed["board_size"],
        "handicap": parsed["handicap"],
        "komi": parsed["komi"],
        "result": parsed["result"],
    }
