from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from rich.console import Console

from src.demo_parser import COMPRESSED_EXTENSIONS, DEMO_EXTENSIONS, extract_compressed_demo
from src.map_asset_server import MapAssetServer, optimized_maps_root

console = Console()

VIEWER_SUBMODULE = "third_party/cs2-2d-demo-viewer"
VIEWER_WEB_REL = Path(VIEWER_SUBMODULE) / "web"
WASM_DIR_REL = VIEWER_WEB_REL / "public" / "wasm"
WASM_FILES = ("csdemoparser.wasm", "wasm_exec.js")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000
PORT_RANGE_END = 3099

REPLAY_MODE_FLAG = "replay_demo"
REPLAY_SMALLEST_FLAG = "replay_demo_smallest"

DEFAULT_SELECTION_REASON = (
    "data/demos içinde oynatılabilir .dem boyutuna göre en küçük geçerli demo "
    "(boş/bozuk dosyalar atlandı, başlık doğrulaması geçti)"
)

CONFLICTING_ANALYSIS_FLAGS: tuple[tuple[str, str], ...] = (
    ("matches", "--matches"),
    ("days", "--days"),
    ("recent", "--recent"),
    ("post_session", "--post-session"),
    ("ai", "--ai"),
    ("export_ai_prompt", "--export-ai-prompt"),
    ("demo_folder", "--demo-folder"),
    ("mechanics", "--mechanics"),
    ("debug_demo", "--debug-demo"),
    ("tara", "--tara"),
    ("suite", "--suite"),
    ("log_counter_strafe", "--log-counter-strafe"),
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def viewer_web_dir() -> Path:
    return repo_root() / VIEWER_WEB_REL


def wasm_dir() -> Path:
    return repo_root() / WASM_DIR_REL


def _is_flag_active(args: argparse.Namespace, attr: str) -> bool:
    if attr in ("matches", "days", "recent", "demo_folder"):
        return getattr(args, attr) is not None
    return bool(getattr(args, attr))


def is_dem_header_valid(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            magic = handle.read(8)
    except OSError:
        return False
    return magic.startswith(b"PBDEMS2") or magic.startswith(b"HL2DEMO")


def _is_compressed_source(path: Path) -> bool:
    name_lower = path.name.lower()
    return any(name_lower.endswith(ext) for ext in COMPRESSED_EXTENSIONS)


def _is_demo_candidate(path: Path) -> bool:
    name_lower = path.name.lower()
    return any(name_lower.endswith(ext) for ext in DEMO_EXTENSIONS)


def iter_demo_candidates(demos_dir: Path) -> list[Path]:
    if not demos_dir.is_dir():
        return []
    files = [
        path
        for path in demos_dir.iterdir()
        if path.is_file() and _is_demo_candidate(path)
    ]
    return sorted(files, key=lambda path: path.name.lower())


@dataclass(frozen=True)
class ValidDemoCandidate:
    source_path: Path
    playable_path: Path
    source_size: int
    playable_size: int


def evaluate_demo_candidate(source: Path) -> tuple[ValidDemoCandidate | None, str]:
    try:
        source_size = source.stat().st_size
    except OSError as exc:
        return None, f"{source.name}: okunamadı ({exc})"

    if source_size <= 0:
        return None, f"{source.name} ({source_size} B): boş dosya"

    resolved, err = resolve_demo_path(str(source))
    if resolved is None:
        return None, f"{source.name} ({source_size} B): {err}"

    try:
        playable_size = resolved.stat().st_size
    except OSError as exc:
        return None, f"{source.name}: oynatılabilir demo okunamadı ({exc})"

    if playable_size <= 0:
        return None, f"{resolved.name}: çıkarılmış demo boş"

    if not is_dem_header_valid(resolved):
        return None, f"{resolved.name}: geçersiz demo başlığı"

    return (
        ValidDemoCandidate(
            source_path=source,
            playable_path=resolved,
            source_size=source_size,
            playable_size=playable_size,
        ),
        "",
    )


def _prefer_candidate(
    existing: ValidDemoCandidate,
    candidate: ValidDemoCandidate,
) -> ValidDemoCandidate:
    existing_compressed = _is_compressed_source(existing.source_path)
    candidate_compressed = _is_compressed_source(candidate.source_path)
    if existing_compressed and not candidate_compressed:
        return candidate
    if candidate_compressed and not existing_compressed:
        return existing
    if candidate.playable_size < existing.playable_size:
        return candidate
    if candidate.playable_size > existing.playable_size:
        return existing
    if candidate.source_size < existing.source_size:
        return candidate
    return existing


def select_smallest_valid_demo(
    demos_dir: Path | None = None,
) -> tuple[Path | None, str, Path | None]:
    folder = demos_dir or (repo_root() / "data" / "demos")
    if not folder.is_dir():
        return None, f"Demo klasörü bulunamadı: {folder}", None

    failures: list[str] = []
    by_playable: dict[Path, ValidDemoCandidate] = {}

    for candidate_path in iter_demo_candidates(folder):
        candidate, err = evaluate_demo_candidate(candidate_path)
        if candidate is None:
            failures.append(err)
            continue

        playable_key = candidate.playable_path.resolve()
        existing = by_playable.get(playable_key)
        if existing is None:
            by_playable[playable_key] = candidate
            continue
        by_playable[playable_key] = _prefer_candidate(existing, candidate)

    if not by_playable:
        if failures:
            return None, "Geçerli demo bulunamadı:\n" + "\n".join(failures), None
        return None, f"Demo klasöründe dosya yok: {folder}", None

    best = min(by_playable.values(), key=lambda item: (item.playable_size, item.source_path.name.lower()))
    return best.playable_path, "", best.source_path


def format_demo_selection(
    path: Path,
    *,
    source_path: Path | None = None,
    reason: str = DEFAULT_SELECTION_REASON,
) -> str:
    playable_bytes = path.stat().st_size
    playable_mb = playable_bytes / (1024 * 1024)
    source = source_path or path
    source_bytes = source.stat().st_size
    source_mb = source_bytes / (1024 * 1024)
    same_file = source.resolve() == path.resolve()

    lines = [
        f"Seçilen demo: {path.name}",
        f"  Tam yol: {path}",
        f"  Oynatılabilir boyut: {playable_bytes} bytes / {playable_mb:.2f} MB",
    ]
    if same_file:
        lines.append(f"  Kaynak dosya: {source.name} (doğrudan .dem)")
    else:
        lines.extend(
            [
                f"  Kaynak dosya: {source.name}",
                f"  Kaynak/sıkıştırılmış boyut: {source_bytes} bytes / {source_mb:.2f} MB",
            ]
        )
    lines.append(f"  Neden: {reason}")
    return "\n".join(lines)


def find_replay_conflicts(args: argparse.Namespace) -> list[str]:
    conflicts: list[str] = []
    for attr, flag in CONFLICTING_ANALYSIS_FLAGS:
        if _is_flag_active(args, attr):
            conflicts.append(flag)
    return conflicts


def viewer_setup_instructions() -> str:
    root = repo_root()
    web = viewer_web_dir()
    submodule = root / VIEWER_SUBMODULE
    return "\n".join(
        [
            "CS2 2D demo viewer hazır değil.",
            "",
            "1) Submodule:",
            f"   git submodule update --init {VIEWER_SUBMODULE}",
            "",
            "2) Web bağımlılıkları (Node/npm gerekli):",
            f'   npm install --prefix "{web}"',
            "",
            "3) WebAssembly parser (Go gerekli):",
            f'   cd "{submodule / "parser"}"',
            "   set GOOS=js",
            "   set GOARCH=wasm",
            '   go build -ldflags="-s -w" -o ..\\web\\public\\wasm\\csdemoparser.wasm .\\wasm.go',
            '   copy "%GOROOT%\\lib\\wasm\\wasm_exec.js" "..\\web\\public\\wasm\\wasm_exec.js"',
            "",
            "Alternatif (make yüklüyse):",
            f'   make -C "{submodule}" wasm',
        ]
    )


def check_viewer_ready() -> tuple[bool, str]:
    web = viewer_web_dir()
    if not web.is_dir():
        return False, viewer_setup_instructions()

    if not (web / "package.json").is_file():
        return False, viewer_setup_instructions()

    if not (web / "node_modules").is_dir():
        return False, (
            f"{viewer_setup_instructions()}\n\n"
            f'Eksik: {web / "node_modules"}\n'
            f'Önce: npm install --prefix "{web}"'
        )

    missing_wasm = [name for name in WASM_FILES if not (wasm_dir() / name).is_file()]
    if missing_wasm:
        return False, (
            f"{viewer_setup_instructions()}\n\n"
            f"Eksik WASM dosyaları: {', '.join(missing_wasm)}"
        )

    if shutil.which("npm") is None:
        return False, "npm bulunamadı. Node.js kurulumu gerekli: https://nodejs.org/"

    return True, ""


def resolve_demo_path(raw: str) -> tuple[Path | None, str]:
    path = Path(raw.strip())
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()

    if not path.exists():
        return None, f"Demo dosyası bulunamadı: {path}"

    name_lower = path.name.lower()
    if any(name_lower.endswith(ext) for ext in COMPRESSED_EXTENSIONS):
        extraction = extract_compressed_demo(path)
        if extraction.get("error"):
            return None, str(extraction["error"])
        out_path = Path(str(extraction["output_path"]))
        if not out_path.is_file():
            return None, f"Demo çıkarılamadı: {path}"
        path = out_path
        name_lower = path.name.lower()

    if not name_lower.endswith(".dem"):
        return None, (
            "Geçersiz demo uzantısı (yalnızca .dem veya desteklenen sıkıştırılmış demo): "
            f"{path.name}"
        )

    return path, ""


def pick_port(host: str = DEFAULT_HOST, start: int = DEFAULT_PORT, end: int = PORT_RANGE_END) -> int | None:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    return None


def build_vite_command(port: int, host: str = DEFAULT_HOST) -> list[str]:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm bulunamadı")
    return [npm, "run", "start", "--", "--host", host, "--port", str(port)]


def build_viewer_url(
    host: str,
    port: int,
    *,
    nickname: str | None = None,
) -> str:
    base = f"http://{host}:{port}/"
    cleaned = (nickname or "").strip()
    if not cleaned:
        return base
    return f"{base}?nickname={quote(cleaned)}"


def start_vite_process(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    popen_kwargs = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "env": merged_env,
    }
    if sys.platform == "win32":
        return subprocess.Popen(subprocess.list2cmdline(cmd), shell=True, **popen_kwargs)
    return subprocess.Popen(cmd, **popen_kwargs)


def start_map_asset_server(host: str = DEFAULT_HOST) -> MapAssetServer | None:
    root = optimized_maps_root(repo_root())
    root.mkdir(parents=True, exist_ok=True)
    try:
        server = MapAssetServer(root, host=host, port=0)
        server.start()
        return server
    except OSError:
        return None


def wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def launch_replay_demo(
    demo_path_raw: str,
    *,
    host: str = DEFAULT_HOST,
    open_browser: bool = True,
    block: bool = True,
    nickname: str | None = None,
) -> int:
    demo_path, err = resolve_demo_path(demo_path_raw)
    if demo_path is None:
        console.print(f"[red]{err}[/red]")
        return 1

    ready, setup_msg = check_viewer_ready()
    if not ready:
        console.print(f"[red]{setup_msg}[/red]")
        return 1

    port = pick_port(host)
    if port is None:
        console.print(
            f"[red]Uygun port bulunamadı ({DEFAULT_PORT}-{PORT_RANGE_END}).[/red]"
        )
        return 1

    web = viewer_web_dir()
    map_server = start_map_asset_server(host)
    vite_env: dict[str, str] = {}
    if map_server is not None:
        vite_env["VITE_MAP_ASSET_BASE"] = map_server.base_url
    try:
        cmd = build_vite_command(port, host)
    except RuntimeError as exc:
        if map_server is not None:
            map_server.stop()
        console.print(f"[red]{exc}[/red]")
        return 1

    try:
        proc = start_vite_process(cmd, web, vite_env)
    except OSError as exc:
        if map_server is not None:
            map_server.stop()
        console.print(f"[red]Viewer sunucusu başlatılamadı: {exc}[/red]")
        return 1

    if not wait_for_server(host, port):
        proc.terminate()
        if map_server is not None:
            map_server.stop()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        console.print("[red]Viewer sunucusu zaman aşımına uğradı.[/red]")
        return 1

    url = build_viewer_url(host, port, nickname=nickname)
    console.print()
    console.print("[bold cyan]CS2 2D Replay Viewer[/bold cyan]")
    console.print(f"Viewer: [link={url}]{url}[/link]")
    console.print(f"Demo: [bold]{demo_path}[/bold]")
    if map_server is not None:
        console.print(f"Map assets: [link={map_server.base_url}]{map_server.base_url}[/link]")
    console.print()
    console.print(
        "[yellow]Tarayıcı güvenliği nedeniyle demo otomatik yüklenemez.[/yellow]\n"
        "Ana sayfadaki upload alanından demo dosyanızı seçin; ardından player açılır."
    )

    if open_browser:
        webbrowser.open(url)

    if block:
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        finally:
            if map_server is not None:
                map_server.stop()
    elif map_server is not None:
        map_server.stop()

    return 0
