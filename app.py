#!/usr/bin/env python3
"""Local dashboard server for the Redrob Scout Arena."""
from __future__ import annotations
import json
import mimetypes
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
OUTPUTS = ROOT / "outputs"
CSV_PATH = OUTPUTS / "team_redrob_fifa_sample_top50.csv"
PAYLOAD_PATH = OUTPUTS / "dashboard_payload.json"


def ensure_outputs() -> None:
    if not CSV_PATH.exists() or not PAYLOAD_PATH.exists():
        subprocess.run([sys.executable, str(ROOT / "ranker.py"), "--candidates", str(ROOT / "data" / "sample_candidates.json"), "--output", str(CSV_PATH), "--dashboard-json", str(PAYLOAD_PATH), "--top", "50"], check=True, cwd=ROOT)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, data: bytes, content_type: str = "text/plain; charset=utf-8", status: int = 200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        ensure_outputs()
        path = unquote(self.path.split("?", 1)[0])
        if path in {"/", "/index.html"}:
            return self._serve_file(STATIC / "index.html")
        if path == "/api/payload":
            return self._serve_file(PAYLOAD_PATH, "application/json; charset=utf-8")
        if path == "/download/csv":
            return self._serve_file(CSV_PATH, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="team_redrob_fifa_sample_top50.csv"'})
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            return self._serve_file(STATIC / rel)
        self._send(b"Not found", status=404)

    def _serve_file(self, file_path: Path, content_type: str | None = None, extra=None):
        if not file_path.exists() or not file_path.is_file():
            return self._send(b"Not found", status=404)
        ctype = content_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._send(file_path.read_bytes(), ctype, extra=extra)


def main():
    ensure_outputs()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("Redrob Scout Arena running at http://localhost:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
