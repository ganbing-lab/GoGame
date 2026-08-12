"""
GoGame HTTP Server (robust)
=============================
启动: python server.py --port 8080
"""

import http.server
import json
import os
import sys
import time
import uuid
import threading
import urllib.parse
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from gogame.core import GoGame
from gogame.config import BOARD_SIZE, COLOR_EMPTY, COLOR_BLACK, COLOR_WHITE, MARK_NEUTRAL
from gogame.board_config import BoardConfig

MARK_CYCLE = [COLOR_WHITE, COLOR_BLACK, MARK_NEUTRAL]

# 超时配置
ROOM_CLEANUP_SEC = 600       # 10 分钟无活动删除房间
PLAYER_TIMEOUT_SEC = 120     # 2 分钟无心跳标记离线
HEARTBEAT_INTERVAL = 60      # 清洁线程间隔
MAX_BODY_BYTES = 8192        # 请求体上限


class Room:
    def __init__(self, room_id: str, board_config: BoardConfig = None):
        self.id = room_id
        disabled = board_config.disabled if board_config else set()
        self.game = GoGame(disabled=disabled)
        self.disabled = disabled
        self.board_name = board_config.name if board_config else "19路标准棋盘"
        self.players = {}
        self.tokens = {}
        self.mode = "playing"
        self.marks = {}
        self.score_final = False
        self.created_at = time.time()
        self.last_activity = time.time()
        self._heartbeats = {}  # token → last poll timestamp
        self._last_action_time = {}  # token → last action timestamp

    def add_player(self, token: str, color: int, name: str):
        self.players[token] = {"color": color, "name": name}
        self.tokens[token] = color
        self._heartbeats[token] = time.time()
        self._last_action_time[token] = 0
        self.last_activity = time.time()

    def touch(self, token: str = ""):
        self.last_activity = time.time()
        if token:
            self._heartbeats[token] = time.time()

    def is_player_online(self, token: str) -> bool:
        last = self._heartbeats.get(token, 0)
        return (time.time() - last) < PLAYER_TIMEOUT_SEC

    def active_players(self) -> int:
        return sum(1 for t in self.tokens if self.is_player_online(t))

    def enter_scoring(self):
        self.mode = "scoring"
        self.marks = {}
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if (r, c) in self.disabled:
                    continue
                cell = self.game.board[r][c]
                if cell == COLOR_EMPTY:
                    self.marks[(r, c)] = MARK_NEUTRAL
                elif cell == COLOR_BLACK:
                    self.marks[(r, c)] = COLOR_BLACK
                elif cell == COLOR_WHITE:
                    self.marks[(r, c)] = COLOR_WHITE

    def mark_region(self, r: int, c: int):
        region = self.game.mark_region_at(r, c)
        if not region:
            return
        first = next(iter(region))
        current = self.marks.get(first, MARK_NEUTRAL)
        try:
            idx = MARK_CYCLE.index(current)
        except ValueError:
            idx = 0
        nxt = MARK_CYCLE[(idx + 1) % len(MARK_CYCLE)]
        for pt in region:
            self.marks[pt] = nxt

    def compute_score(self) -> dict:
        from gogame.config import KOMI
        b, w = 0.0, 0.0
        for owner in self.marks.values():
            if owner == COLOR_BLACK:
                b += 1
            elif owner == COLOR_WHITE:
                w += 1
            elif owner == MARK_NEUTRAL:
                b += 0.5; w += 0.5
        wc = w + KOMI / 2
        return {
            "black_raw": b, "white_raw": w, "white_komi": wc,
            "diff": b - wc,
        }

    def state(self, token: str = "") -> dict:
        your_color = self.tokens.get(token)
        d = {
            "room_id": self.id,
            "board": [row[:] for row in self.game.board],
            "current": self.game.current,
            "captured_black": self.game.captured[COLOR_BLACK],
            "captured_white": self.game.captured[COLOR_WHITE],
            "game_over": self.game.game_over,
            "winner": self.game.winner,
            "move_count": len(self.game.moves),
            "your_color": your_color,
            "disabled": [[r, c] for r, c in sorted(self.disabled)],
            "board_name": self.board_name,
            "mode": self.mode,
            "players_online": {
                "black": any(self.is_player_online(t) for t, c in self.tokens.items()
                             if c == COLOR_BLACK),
                "white": any(self.is_player_online(t) for t, c in self.tokens.items()
                             if c == COLOR_WHITE),
            },
            "players": {
                "black": next((p["name"] for p in self.players.values()
                               if p["color"] == COLOR_BLACK), None),
                "white": next((p["name"] for p in self.players.values()
                               if p["color"] == COLOR_WHITE), None),
            },
        }
        if self.mode == "scoring":
            d["marks"] = {f"{r},{c}": v for (r, c), v in self.marks.items()}
            d["score"] = self.compute_score()
            d["score_final"] = self.score_final
        return d


class GameServer:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self._lock = threading.Lock()

    def create_room(self, board_config: BoardConfig = None) -> str:
        rid = uuid.uuid4().hex[:6]
        with self._lock:
            self.rooms[rid] = Room(rid, board_config)
        return rid

    def get_room(self, room_id: str) -> Room | None:
        with self._lock:
            return self.rooms.get(room_id)

    def cleanup(self):
        now = time.time()
        with self._lock:
            stale = [rid for rid, r in self.rooms.items()
                     if now - r.last_activity > ROOM_CLEANUP_SEC]
            for rid in stale:
                del self.rooms[rid]


# ── 输入校验 ──
def _valid_pos(r, c, disabled):
    return isinstance(r, int) and isinstance(c, int) and \
           0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and \
           (r, c) not in disabled

def _valid_coord(val):
    return isinstance(val, int) or (isinstance(val, (int, float)) and val == int(val))


class Handler(http.server.BaseHTTPRequestHandler):
    server_instance: GameServer = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")

    # ── 工具 ──
    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY_BYTES:
            return {}
        try:
            return json.loads(self.rfile.read(n)) if n > 0 else {}
        except (json.JSONDecodeError, Exception):
            return {}

    def _send(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _err(self, msg, status=400):
        self._send({"error": msg, "code": status}, status)

    def _path_parts(self):
        p = urllib.parse.urlparse(self.path)
        return p.path.rstrip("/"), dict(urllib.parse.parse_qsl(p.query))

    @staticmethod
    def _last_part(path: str) -> str:
        return path.rstrip("/").rsplit("/", 1)[-1]

    # ── 静态文件 ──
    def _serve_file(self, rel: str, mime: str):
        root = Path(__file__).resolve().parent / "static"
        fp = (root / rel).resolve()
        if not str(fp).startswith(str(root)):
            return self._err("Forbidden", 403)
        if not fp.is_file():
            return self._err("Not found", 404)
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    # ── GET ──
    def do_GET(self):
        path, q = self._path_parts()
        s = self.server_instance

        if path in ("", "/"):
            return self._serve_file("index.html", "text/html; charset=utf-8")

        if path == "/api/health":
            total = len(s.rooms)
            active = sum(1 for r in s.rooms.values() if r.active_players() > 0)
            return self._send({"status": "ok", "rooms": total, "active_rooms": active})

        if path.startswith("/api/state/"):
            room = s.get_room(self._last_part(path))
            if not room:
                return self._err("房间不存在或已过期", 404)
            token = q.get("token", "")
            if token and token not in room.tokens:
                return self._send(room.state(""))  # 观战模式
            room.touch(token)
            return self._send(room.state(token))

        if path == "/api/boards":
            bd = _project_root / "boards"
            boards = []
            if bd.is_dir():
                for f in sorted(bd.glob("*.json")):
                    try:
                        cfg = BoardConfig.load(str(f))
                        boards.append(dict(name=cfg.name, file=f.name,
                                           disabled=len(cfg.disabled)))
                    except Exception:
                        pass
            return self._send({"boards": boards})

        self._err("Not found", 404)

    # ── POST ──
    def do_POST(self):
        path, q = self._path_parts()
        s = self.server_instance
        body = self._read_json()

        # 创建房间
        if path == "/api/create":
            board_file = body.get("board", "")
            bc = None
            if board_file:
                bp = _project_root / "boards" / board_file
                if bp.is_file():
                    try:
                        bc = BoardConfig.load(str(bp))
                    except Exception:
                        pass
            rid = s.create_room(bc)
            room = s.get_room(rid)
            token = uuid.uuid4().hex[:8]
            name = str(body.get("name", "黑方"))[:12]
            room.add_player(token, COLOR_BLACK, name)
            return self._send(dict(room_id=rid, token=token,
                                    color=COLOR_BLACK, state=room.state(token)))

        # 加入房间
        if path.startswith("/api/join/"):
            room = s.get_room(self._last_part(path))
            if not room:
                return self._err("房间不存在或已过期", 404)
            if room.mode == "scoring" and room.score_final:
                return self._err("对局已结束", 400)
            has_black = any(c == COLOR_BLACK for c in room.tokens.values())
            color = COLOR_WHITE if has_black else COLOR_BLACK
            for c in room.tokens.values():
                if c == color:
                    return self._err("房间已满", 400)
            token = uuid.uuid4().hex[:8]
            name = str(body.get("name", "白方" if color == COLOR_WHITE else "黑方"))[:12]
            room.add_player(token, color, name)
            return self._send(dict(room_id=room.id, token=token,
                                    color=color, state=room.state(token)))

        # 动作
        if path.startswith("/api/action/"):
            room = s.get_room(self._last_part(path))
            if not room:
                return self._err("房间不存在或已过期", 404)
            token = str(body.get("token", ""))
            act = str(body.get("action", ""))

            if not token or not act:
                return self._err("缺少参数", 400)

            # 非玩家动作（观战者也能触发的）
            if act == "end_game":
                if room.mode != "playing":
                    return self._err("当前不在对局中", 400)
                room.game.game_over = True
                room.enter_scoring()
                room.touch(token)
                return self._send(room.state(token))

            # 需要是玩家
            color = room.tokens.get(token)
            if color is None:
                return self._err("你不是本局玩家", 403)

            now = time.time()
            room.touch(token)

            # 防抖：同一玩家两次操作至少间隔 200ms
            last = room._last_action_time.get(token, 0)
            if now - last < 0.2:
                return self._err("操作过快，请稍后", 429)
            room._last_action_time[token] = now

            # ── 对局中 ──
            if room.mode == "playing":
                if room.game.current != color:
                    return self._err("还没轮到你", 400)

                if act == "move":
                    r = body.get("r"); c = body.get("c")
                    if not (_valid_coord(r) and _valid_coord(c)):
                        return self._err("坐标无效", 400)
                    r, c = int(r), int(c)
                    if not _valid_pos(r, c, room.disabled):
                        return self._err("此处不可落子", 400)
                    if room.game.play(r, c) == -1:
                        return self._err("此处不能落子", 400)

                elif act == "pass":
                    ended = room.game.pass_move()
                    if ended:
                        room.enter_scoring()

                elif act == "resign":
                    room.game.resign()

                else:
                    return self._err(f"未知操作: {act}", 400)

            # ── 计分中 ──
            elif room.mode == "scoring":
                if act == "mark":
                    r = body.get("r"); c = body.get("c")
                    if not (_valid_coord(r) and _valid_coord(c)):
                        return self._err("坐标无效", 400)
                    r, c = int(r), int(c)
                    if not _valid_pos(r, c, room.disabled):
                        return self._err("坐标无效", 400)
                    room.mark_region(r, c)

                elif act == "confirm":
                    room.score_final = True

                elif act == "cancel_scoring":
                    room.mode = "playing"
                    room.game.game_over = False
                    room.marks = {}
                    room.score_final = False

                else:
                    return self._err(f"未知操作: {act}", 400)
            else:
                return self._err(f"未知状态", 500)

            return self._send(room.state(token))

        self._err("Not found", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()


# ═══════════════════════════════════════════
def main():
    import argparse
    ap = argparse.ArgumentParser(description="GoGame HTTP Server")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    gs = GameServer()
    Handler.server_instance = gs

    def _cleanup():
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            gs.cleanup()
    threading.Thread(target=_cleanup, daemon=True).start()

    httpd = http.server.HTTPServer((args.host, args.port), Handler)
    httpd.timeout = 30
    print(f"  GoGame Server  http://0.0.0.0:{args.port}")
    print(f"  Ctrl+C to stop")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("  Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
