"""Synthetic HTTP/SSE listener, used only in an exclusively owned Docker network."""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ["VIGIL_PROXY_QA_VERSION"]
assert VERSION in {"original", "replacement"}
assert os.getuid() == os.getgid() == 10001


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # fixture never logs a URI or request body

    def do_GET(self):
        if self.path == "/api/v1/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            frame = f"event: qa.ready\ndata: {json.dumps({'version': VERSION})}\n\n".encode()
            try:
                self.wfile.write(f"{len(frame):x}\r\n".encode() + frame + b"\r\n")
                self.wfile.flush()
                time.sleep(5)  # headers/frame must reach the client before body completion
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if self.path not in {"/health/ready", "/api/v1/qa"}:
            self.send_error(404)
            return
        body = json.dumps({"version": VERSION}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
