# -*- coding: utf-8 -*-
"""
RC2 搞机工具箱 v4.0 - 本地 HTTP 服务器
前端用 Edge --app 模式加载，界面是真正的 HTML/CSS（液态玻璃 + 圆角 + 动效）
后端 API 通过 /api/<method> 暴露

作者：软糖布丁
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import engine as _E
except Exception:
    _E = None

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "app"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import engine as E
import features as F

UI_DIR = os.path.join(_HERE, "ui")
UI_BASE = None  # 可由 run_app 覆盖
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def res_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _HERE


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE


class Handler(BaseHTTPRequestHandler):
    api = None

    def log_message(self, *a):
        pass

    def _stream(self):
        """MJPEG 推流：不断把设备截图作为 multipart 帧推给浏览器（免 PIL）"""
        import subprocess as sp
        try:
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            fw = self.wfile
            while True:
                data = b""
                try:
                    pr = sp.run([_E.ADB, "exec-out", "screencap", "-p"],
                                capture_output=True, timeout=20,
                                creationflags=0x08000000)
                    data = pr.stdout or b""
                except Exception:
                    data = b""
                if not data:
                    break
                fw.write(b"--frame\r\nContent-Type: image/png\r\n")
                fw.write(("Content-Length: %d\r\n\r\n" % len(data)).encode())
                fw.write(data)
                fw.write(b"\r\n")
                fw.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        path = p.path
        if path == "/stream":
            return self._stream()
        if path == "/" or path == "":
            path = "/index.html"
        if path.startswith("/api/"):
            self._api(path[5:], {})
            return
        # 自定义壁纸（存在 .data/wallpaper.<ext>）
        if path == "/wallpaper":
            wp = None
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                cand = os.path.join(app_dir(), ".data", "wallpaper" + ext)
                if os.path.isfile(cand):
                    wp = cand
                    break
            if not wp:
                self._send(404, b"no wallpaper", "text/plain")
                return
            try:
                with open(wp, "rb") as f:
                    data = f.read()
                ext = os.path.splitext(wp)[1].lower()
                self._send(200, data, MIME.get(ext, "image/jpeg"))
            except Exception:
                self._send(500, b"error", "text/plain")
            return
        # 静态文件
        rel = path.lstrip("/")
        base = UI_BASE or os.path.join(res_dir(), "ui")
        full = os.path.normpath(os.path.join(base, rel))
        if not full.startswith(os.path.normpath(base)):
            self._send(403, b"forbidden", "text/plain")
            return
        if not os.path.isfile(full):
            self._send(404, b"not found", "text/plain")
            return
        ext = os.path.splitext(full)[1].lower()
        try:
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, MIME.get(ext, "application/octet-stream"))
        except Exception:
            self._send(500, b"error", "text/plain")

    def do_POST(self):
        p = urllib.parse.urlparse(self.path)
        if not p.path.startswith("/api/"):
            self._send(404, b"not found", "text/plain")
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace") if n else "{}"
        try:
            args = json.loads(body)
        except Exception:
            args = {}
        self._api(p.path[5:], args)

    def _api(self, method, args):
        if not self.api or not hasattr(self.api, method):
            self._send(200, json.dumps({"ok": False, "msg": "unknown api: " + method},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        try:
            fn = getattr(self.api, method)
            if isinstance(args, dict) and args:
                if "args" in args:
                    result = fn(*args["args"])
                else:
                    result = fn(**args)
            else:
                result = fn()
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
        except Exception as e:
            result = json.dumps({"ok": False, "msg": str(e)}, ensure_ascii=False)
        self._send(200, result.encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass


def find_port(start=47800, tries=60):
    for p in range(start, start + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            s.close()
            continue
    return start


def serve(api, port):
    Handler.api = api
    httpd = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
