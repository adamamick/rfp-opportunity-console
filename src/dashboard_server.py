#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
REPORT_JSON = PROJECT_ROOT / "reports" / "opportunities_latest.json"
SCANNER = PROJECT_ROOT / "src" / "opportunity_scanner.py"


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_latest_report(self) -> dict:
        if not REPORT_JSON.exists():
            return {
                "generated_at": "-",
                "total_items": 0,
                "new_items": 0,
                "high_priority": 0,
                "medium_priority": 0,
                "items": [],
            }
        return json.loads(REPORT_JSON.read_text())

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
        if path == "/styles.css":
            return self._send_file(WEB_ROOT / "styles.css", "text/css; charset=utf-8")
        if path == "/app.js":
            return self._send_file(WEB_ROOT / "app.js", "application/javascript; charset=utf-8")
        if path == "/api/latest":
            return self._send_json(self._read_latest_report())
        if path == "/api/ping":
            return self._send_json({"ok": True, "service": "dashboard"})
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._send_json({"error": "Invalid JSON body."}, HTTPStatus.BAD_REQUEST)

        min_level = str(payload.get("min_level", "MEDIUM")).upper()
        days = int(payload.get("days", 90))
        max_items = int(payload.get("max_items", 300))
        use_cached = bool(payload.get("use_cached", False))

        cmd = [
            "python3",
            str(SCANNER),
            "--days",
            str(days),
            "--max-items",
            str(max_items),
            "--min-level",
            min_level,
        ]

        if use_cached:
            cmd += [
                "--feed-url",
                str(PROJECT_ROOT / "data" / "feed_pages.xml"),
                "--feed-url",
                str(PROJECT_ROOT / "data" / "feed_news.xml"),
                "--feed-url",
                str(PROJECT_ROOT / "data" / "feed_agenda.xml"),
            ]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except Exception as exc:
            return self._send_json({"error": f"Failed to execute scanner: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        if proc.returncode != 0:
            return self._send_json(
                {
                    "error": "Scanner returned non-zero exit code.",
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        report = self._read_latest_report()
        stdout_summary = " ".join(line.strip() for line in proc.stdout.splitlines()[-3:] if line.strip())
        self._send_json({"report": report, "stdout_summary": stdout_summary})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Opportunity Dashboard server.")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8787")), help="Port to bind.")
    parser.add_argument("--open", action="store_true", help="Open dashboard URL in default browser.")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    display_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{display_host}:{args.port}"
    print(f"Dashboard running at {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
