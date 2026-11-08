"""A local stand-in for Slack: the Web API methods the harness calls, a response_url
endpoint, and a Socket Mode websocket on a plain port, which slack_sdk's built-in client
accepts for testing. Requests are recorded so a test can assert on what Slack would see."""

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import struct
import threading
import time
from urllib.parse import parse_qs

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FakeSlack:
    def __init__(self):
        self.calls = []
        self.acks = []
        self.responses = []
        self.client = None
        self._ts = 0
        self._lock = threading.Lock()
        self._ws = socket.socket()
        self._ws.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._ws.bind(("127.0.0.1", 0))
        self._ws.listen()
        self.ws_port = self._ws.getsockname()[1]
        self._http = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._http.server_port}/api/"
        self.response_url = f"http://127.0.0.1:{self._http.server_port}/response/1"
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self._http.shutdown()
        self._http.server_close()
        self._ws.close()
        if self.client:
            self.client.close()

    # --- what a test reads ---

    def wait(self, predicate, seconds=10):
        deadline = time.time() + seconds
        while time.time() < deadline:
            with self._lock:
                found = predicate()
            if found:
                return found
            time.sleep(0.05)
        raise AssertionError("the fake Slack never saw what the test waited for")

    def methods(self, name):
        return [body for method, body in self.calls if method == name]

    def push(self, envelope_id, kind, payload):
        self._send(json.dumps({"envelope_id": envelope_id, "type": kind, "payload": payload,
                               "accepts_response_payload": kind == "slash_commands"}))

    # --- the Web API ---

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                if "json" in (self.headers.get("Content-Type") or ""):
                    body = json.loads(raw or "{}")
                else:
                    body = {key: values[0] for key, values in parse_qs(raw).items()}
                path = self.path.split("?")[0]
                with fake._lock:
                    if path.startswith("/response/"):
                        fake.responses.append(body)
                        reply = {"ok": True}
                    else:
                        method = path.rsplit("/", 1)[-1]
                        fake.calls.append((method, body))
                        reply = fake._reply(method, body)
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler

    def _reply(self, method, body):
        if method == "apps.connections.open":
            return {"ok": True, "url": f"ws://127.0.0.1:{self.ws_port}/link"}
        if method == "conversations.open":
            return {"ok": True, "channel": {"id": "D0SPRINGER"}}
        if method == "auth.test":
            return {"ok": True, "team": "Fake", "user_id": "B0BOT"}
        if method in ("chat.postMessage", "chat.update"):
            self._ts += 1
            return {"ok": True, "channel": body.get("channel"), "ts": body.get("ts") or f"1700000000.{self._ts:06d}"}
        return {"ok": True}

    # --- Socket Mode ---

    def _accept(self):
        while True:
            try:
                conn, _ = self._ws.accept()
            except OSError:
                return
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            key = next(line.split(":", 1)[1].strip() for line in request.decode().split("\r\n")
                       if line.lower().startswith("sec-websocket-key"))
            accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            self.client = conn
            self._send(json.dumps({"type": "hello", "num_connections": 1}))
            threading.Thread(target=self._read, args=(conn,), daemon=True).start()

    def _frame(self, opcode, data):
        header = bytes([0x80 | opcode])
        if len(data) < 126:
            header += bytes([len(data)])
        elif len(data) < 65536:
            header += bytes([126]) + struct.pack("!H", len(data))
        else:
            header += bytes([127]) + struct.pack("!Q", len(data))
        return header + data

    def _send(self, text, opcode=1):
        self.client.sendall(self._frame(opcode, text.encode() if isinstance(text, str) else text))

    def _recv_exact(self, conn, n):
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                raise ConnectionError
            data += chunk
        return data

    def _read(self, conn):
        try:
            while True:
                first, second = self._recv_exact(conn, 2)
                opcode, length = first & 0x0F, second & 0x7F
                if length == 126:
                    length = struct.unpack("!H", self._recv_exact(conn, 2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", self._recv_exact(conn, 8))[0]
                mask = self._recv_exact(conn, 4) if second & 0x80 else b"\0\0\0\0"
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._recv_exact(conn, length)))
                if opcode == 9:
                    conn.sendall(self._frame(10, data))
                elif opcode == 8:
                    return
                elif opcode == 1:
                    with self._lock:
                        self.acks.append(json.loads(data))
        except (ConnectionError, OSError):
            return
