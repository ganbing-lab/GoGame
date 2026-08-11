"""
P2P 联机模块 — 基于 TCP 的简单对等连接。

协议（JSON 行，\\n 分隔）：
  客户端→服务端: {"type":"hello","name":"..."}
  服务端→客户端: {"type":"hello","name":"...","disabled":[[r,c],...]}
  双向: {"type":"move","r":R,"c":C}
  双向: {"type":"pass"}
  双向: {"type":"resign"}

主机（黑方）调用 serve(port) 监听，客机（白方）调用 connect(host, port)。
双方通过 after() 回调将网络消息注入 UI 主线程，线程安全。
"""

import socket
import json
import threading
import select


class Peer:
    """单个对等连接，非阻塞读写 JSON 行。"""

    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self._buf = b""
        self.alive = True

    def send(self, obj):
        """发送 JSON 行（线程安全，单 writer 模式）。"""
        try:
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            self.sock.sendall(line.encode("utf-8"))
            return True
        except (OSError, BrokenPipeError, ConnectionResetError):
            self.alive = False
            return False

    def recv(self):
        """非阻塞读取一条 JSON 行。无完整行返回 None，断开返回 None+alive=False。"""
        try:
            ready, _, _ = select.select([self.sock], [], [], 0)
            if not ready:
                return None
            data = self.sock.recv(4096)
            if not data:
                self.alive = False
                return None
        except (OSError, ConnectionResetError):
            self.alive = False
            return None

        self._buf += data
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            try:
                return json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue  # skip corrupt lines
        return None

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ── 事件回调类型 ──
# on_message(peer, msg_dict)
# on_disconnect(peer)


class GoNetwork:
    """
    联机管理器。
    - 非阻塞主循环由 tkinter after() 驱动。
    - 所有回调在主线程执行。
    """

    def __init__(self, on_message, on_disconnect=None, on_connected=None):
        self._peer = None
        self._server_sock = None
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._on_connected = on_connected
        self._running = False

    # ── 公共 API ──

    def start_server(self, port: int, name: str = "主机"):
        """在后台线程启动监听。连接建立后回调 on_connected。"""
        self._running = True
        t = threading.Thread(target=self._listen, args=(port, name), daemon=True)
        t.start()

    def connect_to(self, host: str, port: int, name: str = "客机"):
        """在后台线程连接主机。连接建立后回调 on_connected。"""
        self._running = True
        t = threading.Thread(target=self._dial, args=(host, port, name), daemon=True)
        t.start()

    def send(self, obj):
        """发送 JSON 消息。"""
        if self._peer:
            self._peer.send(obj)

    def poll(self):
        """每帧调用，非阻塞接收消息。"""
        if not self._peer:
            return
        msg = self._peer.recv()
        if msg is not None:
            self._on_message(self._peer, msg)
        if not self._peer.alive and self._on_disconnect:
            self._on_disconnect(self._peer)

    def is_connected(self):
        return self._peer is not None and self._peer.alive

    def disconnect(self):
        self._running = False
        if self._peer:
            self._peer.close()
            self._peer = None
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

    # ── 内部 ──

    def _resolve(self, host: str, port: int):
        """解析地址，优先 IPv6，回退 IPv4。"""
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except socket.gaierror:
            infos = []
        for family, socktype, proto, canonname, sa in infos:
            try:
                s = socket.socket(family, socktype, proto)
                s.settimeout(5)
                s.connect(sa)
                return s, sa
            except (OSError, socket.timeout):
                continue
        return None, None

    def _dial(self, host: str, port: int, name: str):
        try:
            sock, addr = self._resolve(host, port)
            if sock is None:
                if self._on_disconnect:
                    self._on_disconnect(None)
                return
            sock.settimeout(None)  # blocking → non-blocking for poll
            self._peer = Peer(sock, addr)
            self._peer.send({"type": "hello", "name": name})
            if self._on_connected:
                self._on_connected(self._peer)
        except Exception:
            if self._on_disconnect:
                self._on_disconnect(None)

    def _listen(self, port: int, name: str):
        try:
            # 双栈监听：先试 IPv6（双栈），不行就 IPv4
            try:
                self._server_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                self._server_sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_sock.settimeout(5)
            self._server_sock.bind(("", port))
            self._server_sock.listen(1)

            while self._running:
                try:
                    client, addr = self._server_sock.accept()
                except socket.timeout:
                    continue
                client.settimeout(None)
                self._peer = Peer(client, addr)
                # 发送 hello 告知棋盘信息
                try:
                    import gogame.config as _cfg
                    disabled_list = [[r, c] for r, c in sorted(_cfg.DISABLED_CELLS)]
                except Exception:
                    disabled_list = []
                self._peer.send({"type": "hello", "name": name, "disabled": disabled_list})
                if self._on_connected:
                    self._on_connected(self._peer)
                break  # 只接受一个连接
        except Exception:
            if self._on_disconnect:
                self._on_disconnect(None)
        finally:
            try:
                if self._server_sock:
                    self._server_sock.close()
            except OSError:
                pass
