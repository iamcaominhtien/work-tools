"""Web-based GUI for displaying disk scanner results using a local HTTP server and browser."""

import http.server
import json
import os
import platform
import socket
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from typing import Any, Dict, List, Optional

from .models import FileNode, ScanStats


def find_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def node_to_dict_shallow(node: FileNode) -> Dict[str, Any]:
    """Serialize a FileNode without serializing its children recursively."""
    return {
        "name": node.name,
        "path": node.path,
        "size": node.size,
        "is_dir": node.is_dir,
        "file_count": node.file_count,
        "dir_count": node.dir_count,
        "error": node.error,
        "has_children": len(node.children) > 0,
    }


def find_node_by_path(node: FileNode, target_path: str) -> Optional[FileNode]:
    """Hierarchically locate a FileNode matching the target path in O(depth) time."""
    if node.path == target_path:
        return node

    # Normalize paths for comparison (ensure trailing slash or correct prefix matching)
    node_path_norm = node.path.rstrip(os.sep) + os.sep
    target_path_norm = target_path.rstrip(os.sep) + os.sep

    if target_path_norm.startswith(node_path_norm):
        for child in node.children:
            child_path_norm = child.path.rstrip(os.sep)
            if target_path == child.path or target_path_norm.startswith(
                child_path_norm + os.sep
            ):
                res = find_node_by_path(child, target_path)
                if res:
                    return res
    return None


class DiskScannerHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Custom HTTP handler for serving the Disk Scanner Web UI."""

    # Reference to class-level data to serve
    root_node: FileNode = None
    stats: ScanStats = None
    elapsed: float = 0.0

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server logging to keep terminal clean."""
        pass

    def do_GET(self) -> None:
        """Handle GET requests for static content and APIs."""
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)

        if parsed_url.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._get_html_content().encode("utf-8"))

        elif parsed_url.path == "/api/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "root": node_to_dict_shallow(self.root_node),
                "stats": {
                    "total_files": self.stats.total_files,
                    "total_dirs": self.stats.total_dirs,
                    "total_size": self.stats.total_size,
                    "errors": self.stats.errors,
                    "elapsed": self.elapsed,
                },
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed_url.path == "/api/children":
            path_list = query_params.get("path", [])
            if not path_list:
                self.send_response(400)
                self.end_headers()
                return

            target_path = path_list[0]
            node = find_node_by_path(self.root_node, target_path)
            if node:
                # Serialize only the immediate children
                children_data = [
                    node_to_dict_shallow(child) for child in node.sorted_children()
                ]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(children_data).encode("utf-8"))
            else:
                self.send_response(444)  # Path not found
                self.end_headers()
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self) -> None:
        """Handle POST requests, such as opening folders in File Explorer."""
        if self.path == "/api/open":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data.decode("utf-8"))
                target_path = params.get("path")
                if target_path and os.path.exists(target_path):
                    self._open_path_in_explorer(target_path)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
                    return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return

            self.send_response(400)
            self.end_headers()

    def _open_path_in_explorer(self, path: str) -> None:
        """Open path natively based on OS platform."""
        target_path = path
        if not os.path.isdir(path):
            target_path = os.path.dirname(path)

        current_os = platform.system()
        try:
            if current_os == "Windows":
                os.startfile(target_path)
            elif current_os == "Darwin":  # macOS
                subprocess.run(["open", target_path], check=True)
            else:  # Linux / other
                subprocess.run(["xdg-open", target_path], check=True)
        except Exception:
            pass

    def _get_html_content(self) -> str:
        """Return the complete standalone HTML/CSS/JS page code from the local template file."""
        template_path = os.path.join(os.path.dirname(__file__), "index.html")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"<h1>Lỗi tải giao diện: {str(e)}</h1>"


def run_gui(root_node: FileNode, stats: ScanStats, elapsed: float) -> None:
    """Launch the background web server and open the browser interface."""
    # Set data on class
    DiskScannerHTTPHandler.root_node = root_node
    DiskScannerHTTPHandler.stats = stats
    DiskScannerHTTPHandler.elapsed = elapsed

    port = find_free_port()
    server_address = ("127.0.0.1", port)

    # Start server in a background thread so the terminal remains responsive
    httpd = http.server.HTTPServer(server_address, DiskScannerHTTPHandler)
    server_url = f"http://127.0.0.1:{port}"

    print("-" * 60)
    print(f"🎨 Đang chạy máy chủ giao diện web tại: {server_url}")
    print("👉 Hãy mở trình duyệt nếu trang không tự động tải.")
    print("⌨️  Nhấn Ctrl+C để dừng máy chủ.")
    print("-" * 60)

    # Start thread for server
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    # Automatically open default browser
    webbrowser.open(server_url)

    # Wait for keyboard interrupt to stop
    try:
        while True:
            t.join(0.5)
    except KeyboardInterrupt:
        print("\n⛔ Đang dừng máy chủ giao diện web...")
        httpd.shutdown()
        sys.exit(0)
