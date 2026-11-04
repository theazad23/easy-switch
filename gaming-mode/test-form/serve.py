#!/usr/bin/env python3
"""Serve the Gaming Mode test form on the LAN; save submissions; report the current cycle round.
Usage: serve.py <index.html> <results.json> [addr:port]   (default 0.0.0.0:8766)
Started by `gaming-mode-test-form start`."""
import json, os, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FORM = Path(sys.argv[1]); OUT = Path(sys.argv[2])
INDEX = Path(os.path.expanduser("~/.local/state/gaming-mode-diag/index.log"))

def status():
    """Current cycle round from the diag index: {round, total, done, start}."""
    try: lines = INDEX.read_text(errors="replace").splitlines()
    except OSError: return {}
    start = max((i for i, l in enumerate(lines) if " CYCLE start:" in l), default=None)
    if start is None: return {}
    m = re.search(r"CYCLE start: (\d+) rounds", lines[start]); total = int(m.group(1)) if m else 0
    rnd = 0; done = False
    for l in lines[start:]:
        m = re.search(r"CYCLE round (\d+) of", l)
        if m: rnd = int(m.group(1))
        if " CYCLE done" in l or " CYCLE aborted" in l: done = True
    return {"round": rnd, "total": total, "done": done, "start": lines[start][11:19]}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status":
            body = json.dumps(status()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body); return
        if path not in ("/", "/index.html"):
            return self.send_error(404)
        body = FORM.read_bytes()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if self.path != "/submit":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0))
        if n > 100_000:
            return self.send_error(413)
        data = json.loads(self.rfile.read(n))
        data["submitted"] = time.strftime("%F %T")
        OUT.write_text(json.dumps(data, indent=2))
        self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
        self.wfile.write(b"saved")

host, _, port = (sys.argv[3] if len(sys.argv) > 3 else "0.0.0.0:8766").rpartition(":")
ThreadingHTTPServer((host or "0.0.0.0", int(port)), H).serve_forever()
