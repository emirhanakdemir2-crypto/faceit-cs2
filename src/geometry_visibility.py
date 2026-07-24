"""Geometry LoS backend via Awpy VisibilityChecker (map-tri BVH).

Does not auto-download .tri assets. Missing dependency/assets return an
explicit status plus the setup command for the user.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Protocol

from src import suite_config as cfg

UNAVAILABLE = "Unavailable"

CheckerFactory = Callable[[Path], Any]


class VisibilityBackendProtocol(Protocol):
    def is_visible(
        self,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
    ) -> bool: ...


def normalize_map_name(map_name: str | None) -> str:
    if not map_name or not isinstance(map_name, str):
        return ""
    name = map_name.strip().lower().replace("\\", "/").split("/")[-1]
    name = re.sub(r"\.dem$", "", name)
    name = re.sub(r"_scrimmagemap$", "", name)
    return name


def setup_command() -> str:
    return cfg.GEOMETRY_SETUP_COMMAND


def awpy_import_status() -> dict[str, Any]:
    try:
        import awpy  # noqa: F401
        from awpy.visibility import VisibilityChecker  # noqa: F401
        from awpy.data import TRIS_DIR

        version = getattr(__import__("awpy"), "__version__", UNAVAILABLE)
        return {
            "ok": True,
            "version": version,
            "tris_dir": str(TRIS_DIR),
            "status": cfg.GEOMETRY_STATUS_AVAILABLE,
            "setup_command": setup_command(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "version": UNAVAILABLE,
            "tris_dir": UNAVAILABLE,
            "status": cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING,
            "error": str(exc),
            "setup_command": setup_command(),
        }


def default_tris_dir() -> Path | None:
    info = awpy_import_status()
    if not info.get("ok"):
        return None
    try:
        from awpy.data import TRIS_DIR

        return Path(TRIS_DIR)
    except Exception:
        return None


def resolve_tri_path(
    map_name: str | None,
    *,
    tris_dir: Path | None = None,
    require_awpy: bool = True,
) -> dict[str, Any]:
    """Locate map .tri without downloading."""
    if require_awpy and tris_dir is None:
        dep = awpy_import_status()
        if not dep.get("ok"):
            return {
                "status": cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING,
                "map_name": normalize_map_name(map_name) or UNAVAILABLE,
                "tri_path": UNAVAILABLE,
                "setup_command": setup_command(),
                "error": dep.get("error") or "awpy import failed",
            }

    normalized = normalize_map_name(map_name)
    if not normalized:
        return {
            "status": cfg.GEOMETRY_STATUS_UNSUPPORTED_MAP,
            "map_name": UNAVAILABLE,
            "tri_path": UNAVAILABLE,
            "setup_command": setup_command(),
            "error": "map name empty",
        }

    root = Path(tris_dir) if tris_dir is not None else default_tris_dir()
    if root is None:
        return {
            "status": cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING,
            "map_name": normalized,
            "tri_path": UNAVAILABLE,
            "setup_command": setup_command(),
            "error": "TRIS_DIR unavailable",
        }

    if not root.exists():
        return {
            "status": cfg.GEOMETRY_STATUS_TRI_MISSING,
            "map_name": normalized,
            "tri_path": UNAVAILABLE,
            "tris_dir": str(root),
            "setup_command": setup_command(),
            "error": f"tris directory missing: {root}",
        }

    tri_path = root / f"{normalized}.tri"
    if not tri_path.is_file():
        available = sorted(p.stem for p in root.glob("*.tri"))
        return {
            "status": cfg.GEOMETRY_STATUS_UNSUPPORTED_MAP
            if available
            else cfg.GEOMETRY_STATUS_TRI_MISSING,
            "map_name": normalized,
            "tri_path": UNAVAILABLE,
            "tris_dir": str(root),
            "available_maps": available,
            "setup_command": setup_command(),
            "error": f"no .tri for map '{normalized}'",
        }

    return {
        "status": cfg.GEOMETRY_STATUS_AVAILABLE,
        "map_name": normalized,
        "tri_path": str(tri_path.resolve()),
        "tris_dir": str(root),
        "setup_command": setup_command(),
        "error": "",
    }


def _default_checker_factory(tri_path: Path) -> Any:
    from awpy.visibility import VisibilityChecker

    return VisibilityChecker(path=tri_path)


class GeometryVisibilityBackend:
    """Map-cached VisibilityChecker wrapper with injectable factory for tests."""

    def __init__(
        self,
        *,
        tris_dir: Path | None = None,
        checker_factory: CheckerFactory | None = None,
        backend_source: str | None = None,
        backend_version: str | None = None,
    ) -> None:
        self._tris_dir = tris_dir
        self._checker_factory = checker_factory or _default_checker_factory
        self._cache: dict[str, Any] = {}
        self._create_counts: dict[str, int] = {}
        self.backend_source = backend_source or cfg.GEOMETRY_BACKEND_SOURCE
        self.backend_version = backend_version or cfg.GEOMETRY_BACKEND_VERSION_PIN
        self.last_status: dict[str, Any] = {
            "status": cfg.GEOMETRY_STATUS_DEPENDENCY_MISSING,
            "setup_command": setup_command(),
        }

    @property
    def create_counts(self) -> dict[str, int]:
        return dict(self._create_counts)

    def clear_cache(self) -> None:
        self._cache.clear()
        self._create_counts.clear()

    def ensure_map(self, map_name: str | None) -> dict[str, Any]:
        require_awpy = self._tris_dir is None and self._checker_factory is _default_checker_factory
        # Injected tris_dir or factory → tests / offline paths skip awpy import gate.
        if self._tris_dir is not None or self._checker_factory is not _default_checker_factory:
            require_awpy = False
        resolved = resolve_tri_path(
            map_name, tris_dir=self._tris_dir, require_awpy=require_awpy,
        )
        self.last_status = {
            **resolved,
            "backend_source": self.backend_source,
            "backend_version": self.backend_version,
            "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
        }
        if resolved["status"] != cfg.GEOMETRY_STATUS_AVAILABLE:
            return self.last_status

        key = str(resolved["map_name"])
        if key not in self._cache:
            try:
                tri = Path(str(resolved["tri_path"]))
                self._cache[key] = self._checker_factory(tri)
                self._create_counts[key] = self._create_counts.get(key, 0) + 1
            except Exception as exc:
                self.last_status = {
                    "status": cfg.GEOMETRY_STATUS_INIT_FAILED,
                    "map_name": key,
                    "tri_path": resolved.get("tri_path"),
                    "error": str(exc),
                    "setup_command": setup_command(),
                    "backend_source": self.backend_source,
                    "backend_version": self.backend_version,
                    "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
                }
                return self.last_status

        self.last_status["status"] = cfg.GEOMETRY_STATUS_AVAILABLE
        self.last_status["checker_cached"] = True
        self.last_status["create_count_for_map"] = self._create_counts.get(key, 0)
        return self.last_status

    def get_checker(self, map_name: str | None) -> Any | None:
        status = self.ensure_map(map_name)
        if status.get("status") != cfg.GEOMETRY_STATUS_AVAILABLE:
            return None
        return self._cache.get(str(status.get("map_name")))

    def is_visible(
        self,
        map_name: str | None,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
    ) -> dict[str, Any]:
        status = self.ensure_map(map_name)
        base = {
            "backend_source": self.backend_source,
            "backend_version": self.backend_version,
            "measurement_quality": cfg.GEOMETRY_MEASUREMENT_QUALITY,
            "map_name": status.get("map_name", UNAVAILABLE),
            "setup_command": status.get("setup_command", setup_command()),
        }
        if status.get("status") != cfg.GEOMETRY_STATUS_AVAILABLE:
            return {
                **base,
                "status": status.get("status"),
                "visible": UNAVAILABLE,
                "error": status.get("error") or "",
            }
        checker = self._cache.get(str(status.get("map_name")))
        if checker is None:
            return {
                **base,
                "status": cfg.GEOMETRY_STATUS_INIT_FAILED,
                "visible": UNAVAILABLE,
                "error": "checker missing after ensure_map",
            }
        try:
            visible = bool(checker.is_visible(start, end))
            return {
                **base,
                "status": cfg.GEOMETRY_STATUS_AVAILABLE,
                "visible": visible,
                "error": "",
            }
        except Exception as exc:
            return {
                **base,
                "status": cfg.GEOMETRY_STATUS_INIT_FAILED,
                "visible": UNAVAILABLE,
                "error": str(exc),
            }


class FakeVisibilityChecker:
    """Test double: callable returns bool for (start, end)."""

    def __init__(self, visible_fn: Callable[[tuple, tuple], bool] | bool = True) -> None:
        if isinstance(visible_fn, bool):
            self._fn: Callable[[tuple, tuple], bool] = lambda _a, _b: visible_fn
        else:
            self._fn = visible_fn
        self.calls: list[tuple[tuple, tuple]] = []

    def is_visible(self, start: Any, end: Any) -> bool:
        s = tuple(float(x) for x in start)
        e = tuple(float(x) for x in end)
        self.calls.append((s, e))
        return bool(self._fn(s, e))


def make_fake_backend(
    *,
    visible: bool | Callable[[tuple, tuple], bool] = True,
    map_name: str = "de_dust2",
    tris_dir: Path | None = None,
) -> GeometryVisibilityBackend:
    """Build a backend that never touches real .tri files."""
    root = tris_dir or Path(".")
    tri = root / f"{normalize_map_name(map_name)}.tri"

    def factory(_path: Path) -> FakeVisibilityChecker:
        return FakeVisibilityChecker(visible)

    backend = GeometryVisibilityBackend(
        tris_dir=root,
        checker_factory=factory,
        backend_source="fake",
        backend_version="test",
    )
    # Bypass resolve_tri_path file checks by stubbing ensure via pre-seed when
    # used with a real tris_dir that contains the fake .tri path. Callers that
    # pass an empty temp dir should create the placeholder .tri file.
    if not tri.exists():
        # Leave file creation to tests; factory still used once path resolves.
        pass
    return backend
