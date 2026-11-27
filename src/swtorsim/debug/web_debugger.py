"""Local web server for the debugger UI: serves tools/debugger_ui.html and a small JSON API (see debug_api)."""

from __future__ import annotations

import json
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.swtorsim.debug import debug_api

ROOT = Path(__file__).resolve().parents[3]
UI_PATH = ROOT / "tools" / "debugger_ui.html"
STARTED_WITH_VERSION = debug_api.current_code_version()  # the code this process loaded; see ensure_debugger_running


class DebuggerRequestHandler(BaseHTTPRequestHandler):
    server_version = "SwtorSimDebugger/1.0"

    def log_message(self, format, *args):  # keep the console quiet
        pass

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
        elif path.startswith("/icons/"):
            icon = debug_api.find_icon(path[len("/icons/"):])
            if icon is None:
                self._send_json(404, {"error": "no such icon"})
            else:
                self._send(200, icon.read_bytes(), "image/png", cache="public, max-age=86400")
        elif path == "/api/configs":
            self._send_json(200, {**debug_api.handle("configs"), "version": STARTED_WITH_VERSION})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        action = self.path.split("?", 1)[0].removeprefix("/api/")
        if action not in debug_api.ACTIONS:
            self._send_json(404, {"error": f"unknown action: {action}"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            self._send_json(200, debug_api.handle(action, payload))
        except Exception as exc:  # report to the UI instead of dropping the connection
            traceback.print_exc()
            self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})


def launch_debugger(host: str = "127.0.0.1", port: int = 8770, open_browser: bool = True) -> None:
    """Starts the debugger on the first free port from ``port`` and blocks until Ctrl+C."""
    server = None
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), DebuggerRequestHandler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"No free port in {port}-{port + 19}")
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"[OK] SwtorSim debugger running at {url} (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
