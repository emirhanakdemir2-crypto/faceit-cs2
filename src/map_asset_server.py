from __future__ import annotations

import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from src.map_manifest import is_valid_map_name

ROUTE_PREFIX = "/local-map-assets/"
ALLOWED_RELATIVE_FILES = frozenset({"scene.glb", "manifest.json"})
MAP_SEGMENT_PATTERN = re.compile(r"^[a-z0-9_]+$")
LOOPBACK_ORIGIN_PATTERN = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)


def cors_allow_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    if LOOPBACK_ORIGIN_PATTERN.fullmatch(origin):
        return origin
    return None


class MapAssetServerError(RuntimeError):
    pass


def parse_map_asset_path(path: str) -> tuple[str, str] | None:
    if not path.startswith(ROUTE_PREFIX):
        return None
    remainder = path[len(ROUTE_PREFIX) :]
    if not remainder or remainder.endswith("/"):
        return None
    parts = [unquote(part) for part in remainder.split("/") if part]
    if len(parts) != 2:
        return None
    map_name, file_name = parts
    if not MAP_SEGMENT_PATTERN.fullmatch(map_name):
        return None
    if not is_valid_map_name(map_name):
        return None
    if file_name not in ALLOWED_RELATIVE_FILES:
        return None
    if ".." in map_name or ".." in file_name:
        return None
    return map_name, file_name


def resolve_map_asset_file(root: Path, map_name: str, file_name: str) -> Path | None:
    if not is_valid_map_name(map_name) or file_name not in ALLOWED_RELATIVE_FILES:
        return None
    root_resolved = root.resolve()
    candidate = (root_resolved / map_name / file_name).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


class MapAssetRequestHandler(BaseHTTPRequestHandler):
    optimized_root: Path = Path(".")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_cors_headers(self) -> None:
        allowed = cors_allow_origin(self.headers.get("Origin"))
        if not allowed:
            return
        self.send_header("Access-Control-Allow-Origin", allowed)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header(
            "Access-Control-Expose-Headers",
            "Content-Length, Content-Range, Accept-Ranges",
        )

    def _send_error_with_cors(self, code: int) -> None:
        self.send_response(code)
        self._write_cors_headers()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parse_map_asset_path(parsed.path)
        if route is None:
            self._send_error_with_cors(404)
            return
        self.send_response(204)
        self._write_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parse_map_asset_path(parsed.path)
        if route is None:
            self._send_error_with_cors(404)
            return
        map_name, file_name = route
        target = resolve_map_asset_file(self.optimized_root, map_name, file_name)
        if target is None:
            self._send_error_with_cors(404)
            return

        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() == ".glb":
            content_type = "model/gltf-binary"
        elif target.name == "manifest.json":
            content_type = "application/json"

        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            try:
                start_text, end_text = range_header.replace("bytes=", "").split("-", 1)
                start = int(start_text) if start_text else 0
                end = int(end_text) if end_text else len(data) - 1
                end = min(end, len(data) - 1)
                if start > end or start < 0:
                    raise ValueError("invalid range")
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self._write_cors_headers()
                self.end_headers()
                self.wfile.write(chunk)
                return
            except (ValueError, IndexError):
                self._send_error_with_cors(416)
                return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self._write_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parse_map_asset_path(parsed.path)
        if route is None:
            self._send_error_with_cors(404)
            return
        map_name, file_name = route
        target = resolve_map_asset_file(self.optimized_root, map_name, file_name)
        if target is None:
            self._send_error_with_cors(404)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() == ".glb":
            content_type = "model/gltf-binary"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(target.stat().st_size))
        self._write_cors_headers()
        self.end_headers()


class MapAssetServer:
    def __init__(
        self,
        optimized_root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        if host not in {"127.0.0.1", "localhost"}:
            raise MapAssetServerError("map asset server must bind to loopback only")
        self.optimized_root = optimized_root.resolve()
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._httpd is None:
            raise MapAssetServerError("server not started")
        return f"http://{self.host}:{self._httpd.server_address[1]}"

    def start(self) -> None:
        if self._httpd is not None:
            return

        handler_factory: Callable[..., MapAssetRequestHandler] = type(
            "BoundMapAssetRequestHandler",
            (MapAssetRequestHandler,),
            {"optimized_root": self.optimized_root},
        )
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler_factory)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="map-asset-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None


def optimized_maps_root(repo_root: Path) -> Path:
    return repo_root / "data" / "maps3d" / "optimized"
