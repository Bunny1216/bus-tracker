"""
bus_tracker_app.py - one-click launcher for the City Bus Tracker.

Place this file in E:\\bus-tracker (next to the data/ and web/ folders) and run it.
It serves the project root on a free local port (so ../data/ always resolves),
then opens the app in a native window (if pywebview is installed) or in your
default browser.
"""
import functools
import http.server
import mimetypes
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

# When frozen with PyInstaller, bundled files live in sys._MEIPASS.
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
START_PATH = "/web/index.html"

# Windows registry can map .js/.json to wrong types; set them explicitly.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/json", ".json")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler without console log spam."""

    def log_message(self, *args):
        pass


def start_server():
    """Start the HTTP server on a free port (port 0 = OS picks one)."""
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main():
    httpd, port = start_server()
    url = f"http://127.0.0.1:{port}{START_PATH}"
    try:
        import webview  # optional: pip install pywebview
        webview.create_window("City Bus Tracker", url, width=1100, height=750)
        webview.start()  # blocks until the window is closed
    except ImportError:
        webbrowser.open(url)
        print(f"City Bus Tracker running at {url}")
        print("Press Ctrl+C (or close this window) to stop.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
