"""ensure_rotation_builder_running must not mistake an unrelated listener for the builder."""

import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.swtorsim import web_gui


class _OtherPage(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = b"<html><title>SwtorSim - Combat Simulator Dashboard</title><button>Rotation Builder</button></html>"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class BuilderLaunchTests(unittest.TestCase):
    def test_unrelated_listener_on_default_port_is_skipped(self):
        decoy = HTTPServer(("127.0.0.1", 0), _OtherPage)
        port = decoy.server_address[1]
        threading.Thread(target=decoy.serve_forever, daemon=True).start()
        self.addCleanup(decoy.server_close)
        self.addCleanup(decoy.shutdown)
        prev = web_gui._ROTATION_BUILDER_PORT
        web_gui._ROTATION_BUILDER_PORT = None
        self.addCleanup(setattr, web_gui, "_ROTATION_BUILDER_PORT", prev)

        self.assertFalse(web_gui._is_rotation_builder("127.0.0.1", port))
        url = web_gui.ensure_rotation_builder_running(default_port=port)
        self.assertNotEqual(url, f"http://127.0.0.1:{port}")
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertIn(b"<title>SwtorSim - Rotation Builder</title>", resp.read())


if __name__ == "__main__":
    unittest.main()
