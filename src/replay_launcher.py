from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import time
import webbrowser
from pathlib import Path

from rich.console import Console

from src.demo_parser import COMPRESSED_EXTENSIONS, extract_compressed_demo

console = Console()

VIEWER_SUBMODULE = "third_party/cs2-2d-demo-viewer"
VIEWER_WEB_REL = Path(VIEWER_SUBMODULE) / "web"
WASM_DIR_REL = VIEWER_WEB_REL / "public" / "wasm"
WASM_FILES = ("csdemoparser.wasm", "wasm_exec.js")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3000
PORT_RANGE_END = 3099

REPLAY_MODE_FLAG = "replay_demo"

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
) -> int:
    ready, setup_msg = check_viewer_ready()
    if not ready:
        console.print(f"[red]{setup_msg}[/red]")
        return 1

    demo_path, err = resolve_demo_path(demo_path_raw)
    if demo_path is None:
        console.print(f"[red]{err}[/red]")
        return 1

    port = pick_port(host)
    if port is None:
        console.print(
            f"[red]Uygun port bulunamadı ({DEFAULT_PORT}-{PORT_RANGE_END}).[/red]"
        )
        return 1

    web = viewer_web_dir()
    try:
        cmd = build_vite_command(port, host)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=web,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        console.print(f"[red]Viewer sunucusu başlatılamadı: {exc}[/red]")
        return 1

    if not wait_for_server(host, port):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        console.print("[red]Viewer sunucusu zaman aşımına uğradı.[/red]")
        return 1

    url = f"http://{host}:{port}/player"
    console.print()
    console.print("[bold cyan]CS2 2D Replay Viewer[/bold cyan]")
    console.print(f"Viewer: [link={url}]{url}[/link]")
    console.print(f"Demo: [bold]{demo_path}[/bold]")
    console.print()
    console.print(
        "[yellow]Tarayıcı güvenliği nedeniyle demo otomatik yüklenemez.[/yellow]\n"
        "Player sayfasında ekrandan demo dosyanızı seçin."
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

    return 0
