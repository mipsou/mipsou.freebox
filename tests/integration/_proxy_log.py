#!/usr/bin/env python3
"""
Transparent HTTP logging proxy for Freebox debugging.
Listens on localhost:8765, forwards to mafreebox.freebox.fr.
Logs every request/response verbatim.
"""
import json
import socket
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import HTTPError

TARGET_HOST = "mafreebox.freebox.fr"
TARGET_PORT = 80
LISTEN_PORT = 8765
LOG_FILE = "/tmp/proxy_log.txt"

_log_lock = threading.Lock()


def _log(msg):
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(msg + "\n")
        print(msg)


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default logging

    def _forward(self):
        path = self.path
        target_url = "http://%s%s" % (TARGET_HOST, path)

        body = None
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            body = self.rfile.read(length)

        # Build headers for upstream
        fwd_headers = {}
        for k, v in self.headers.items():
            if k.lower() in ("host", "content-length"):
                continue
            fwd_headers[k] = v
        fwd_headers["Host"] = TARGET_HOST

        req = Request(target_url, data=body, headers=fwd_headers, method=self.command)

        _log("=== %s %s ===" % (self.command, path))
        _log("REQ headers: %s" % dict(fwd_headers))
        if body:
            _log("REQ body: %r" % body[:500])

        try:
            with urlopen(req, timeout=15) as resp:
                status = resp.status
                resp_body = resp.read()
                resp_headers = dict(resp.headers)
        except HTTPError as e:
            status = e.code
            resp_body = e.read()
            resp_headers = dict(e.headers)

        _log("RESP %d body: %r" % (status, resp_body[:500]))

        # Reply to client
        self.send_response(status)
        for k, v in resp_headers.items():
            if k.lower() in ("transfer-encoding", "connection"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def do_PUT(self):
        self._forward()

    def do_DELETE(self):
        self._forward()


if __name__ == "__main__":
    open(LOG_FILE, "w").close()  # reset log
    server = HTTPServer(("127.0.0.1", LISTEN_PORT), ProxyHandler)
    print("Proxy listening on localhost:%d → %s" % (LISTEN_PORT, TARGET_HOST))
    server.serve_forever()
