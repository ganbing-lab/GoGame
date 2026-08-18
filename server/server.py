"""
GoGame 联机服务器（状态中继版）
================================
前端（docs/ 网页版）负责围棋规则与界面，本服务器只负责三件事：
  1. 托管 docs/ 静态页面 —— 同源访问，一条命令即可联机对战
  2. 房间管理 —— 创建 / 加入（先到先得，黑先白后）
  3. 状态中继 —— 任一方把"完整局面数据包"提交上来，另一端轮询拉取

没有 WebRTC / NAT 穿透 / 信令服务器那一套，也无需依赖项目引擎
（规则在两端各跑同一份前端引擎，服务器只做权威状态存储）。

启动:  python server.py [--port 8080] [--host 0.0.0.0]
然后浏览器打开 http://<本机IP>:8080/ 即可（页面与 API 同源）。
"""

import argparse
import http.server
import json
import threading
import time
import urllib.parse
import uuid
from pathlib import Path

ROOM_TTL_SEC = 3600           # 房间 1 小时无活动自动清理
CLEANUP_INTERVAL = 60
MAX_BODY_BYTES = 4 * 1024 * 1024   # 全量状态包可能上百 KB

STATIC_ROOT = Path(__file__).resolve().parent.parent / "docs"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Room:
    """一个联机房间：只存最近一次提交的全量状态 + 玩家 token"""

    def __init__(self, rid: str):
        self.id = rid
        self.sync = None          # dict：前端 buildSync() 的完整局面数据包
        self.tokens = {}          # token -> "black" | "white"
        self.last_activity = time.time()

    def touch(self):
        self.last_activity = time.time()

    def is_full(self):
        return len(self.tokens) >= 2


class Server:
    def __init__(self):
        self.rooms: dict = {}
        self.lock = threading.Lock()

    def create_room(self) -> str:
        rid = uuid.uuid4().hex[:6]
        with self.lock:
            self.rooms[rid] = Room(rid)
        return rid

    def get_room(self, rid: str):
        with self.lock:
            return self.rooms.get(rid)

    def cleanup(self):
        now = time.time()
        with self.lock:
            stale = [rid for rid, r in self.rooms.items()
                     if now - r.last_activity > ROOM_TTL_SEC]
            for rid in stale:
                del self.rooms[rid]


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_instance: Server = None

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")

    # ── 工具 ──
    def _read_json(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY_BYTES:
                return {}
            return json.loads(self.rfile.read(n)) if n > 0 else {}
        except Exception:
            return {}

    def _send_json(self, data, status=200):
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
        self._send_json({"error": msg, "code": status}, status)

    def _serve_static(self, rel: str):
        root = STATIC_ROOT.resolve()
        fp = (root / rel).resolve()
        if not str(fp).startswith(str(root)) or not fp.is_file():
            return self._err("Not found", 404)
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(fp.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ── GET ──
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = dict(urllib.parse.parse_qsl(parsed.query))
        s = self.server_instance

        if path == "/api/health":
            return self._send_json({"status": "ok", "rooms": len(s.rooms)})

        if path.startswith("/api/state/"):
            rid = path.rsplit("/", 1)[-1]
            room = s.get_room(rid)
            if not room:
                return self._err("房间不存在或已过期", 404)
            room.touch()
            return self._send_json({
                "sync": room.sync,
                "players": {c: (c in room.tokens.values()) for c in ("black", "white")},
            })

        # 静态页面
        if path == "/":
            return self._serve_static("index.html")
        rel = path.lstrip("/")
        if rel and Path(rel).suffix.lower() in MIME:
            return self._serve_static(rel)
        self._err("Not found", 404)

    # ── POST ──
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        body = self._read_json()
        s = self.server_instance

        # 创建房间（房主执黑）
        if path == "/api/create":
            rid = s.create_room()
            room = s.get_room(rid)
            token = uuid.uuid4().hex[:8]
            room.tokens[token] = "black"
            room.touch()
            return self._send_json({
                "room_id": rid, "token": token, "color": "black",
                "state": room.sync,
            })

        # 加入房间（后到执白）
        if path.startswith("/api/join/"):
            rid = path.rsplit("/", 1)[-1]
            room = s.get_room(rid)
            if not room:
                return self._err("房间不存在或已过期", 404)
            if room.is_full():
                return self._err("房间已满", 400)
            color = "white" if "black" in room.tokens.values() else "black"
            token = uuid.uuid4().hex[:8]
            room.tokens[token] = color
            room.touch()
            return self._send_json({
                "room_id": rid, "token": token, "color": color,
                "state": room.sync,
            })

        # 提交全量状态（任一方每次操作后调用）
        if path.startswith("/api/update/"):
            rid = path.rsplit("/", 1)[-1]
            room = s.get_room(rid)
            if not room:
                return self._err("房间不存在或已过期", 404)
            token = str(body.get("token", ""))
            if token not in room.tokens:
                return self._err("你不是本局玩家", 403)
            sync = body.get("sync")
            if not isinstance(sync, dict):
                return self._err("缺少状态数据", 400)
            room.sync = sync
            room.touch()
            return self._send_json({"ok": True})

        self._err("Not found", 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    ap = argparse.ArgumentParser(description="GoGame 联机服务器（状态中继）")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    srv = Server()
    Handler.server_instance = srv

    def _cleanup():
        while True:
            time.sleep(CLEANUP_INTERVAL)
            srv.cleanup()

    threading.Thread(target=_cleanup, daemon=True).start()

    httpd = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.timeout = 30
    print(f"  GoGame 联机服务器: http://0.0.0.0:{args.port}")
    print(f"  浏览器打开 http://<本机IP>:{args.port}/ 即可开始对弈（页面与 API 同源）")
    print("  Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("  Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()

