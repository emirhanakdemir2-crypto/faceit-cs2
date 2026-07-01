from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.achievements import analyze_achievements, render_achievements_markdown
from src.aim_analyzer import analyze_aim, render_aim_markdown
from src.ask_ai_export import render_ask_ai_markdown
from src.benchmarks import analyze_benchmarks, render_benchmarks_markdown
from src.dashboard_analyzer import analyze_dashboard, render_dashboard_markdown
from src.data_library import analyze_data_library, render_data_library_markdown
from src.focus_areas import analyze_focus_areas, render_focus_areas_markdown
from src.general_analyzer import analyze_general, render_general_markdown
from src.home_analyzer import analyze_home, render_home_markdown
from src.maps_analyzer import analyze_maps, render_maps_markdown
from src.matches_analyzer import analyze_matches, render_matches_markdown
from src.operation_planner import analyze_operation, render_operation_markdown
from src.sessions_analyzer import analyze_sessions, render_sessions_markdown
from src.training_planner import analyze_training, render_training_markdown
from src.utility_analyzer import analyze_utility, render_utility_markdown


def build_analytics_suite(
    processed_payload: dict[str, Any],
    *,
    memory: dict[str, Any] | None = None,
    demo_folder: str | Path | None = None,
) -> dict[str, Any]:
    """Tüm analytics suite bölümlerini üretir."""
    nickname = (processed_payload.get("profile") or {}).get("nickname") or "player"
    profile = processed_payload.get("profile") or {}
    summary = processed_payload.get("summary") or {}
    matches = processed_payload.get("matches") or []
    map_stats = processed_payload.get("map_stats") or {}
    mechanics_lab = processed_payload.get("mechanics_lab") or {}
    agg = mechanics_lab.get("aggregated") or {}
    mech = agg.get("mechanics") or {}
    impact = agg.get("impact") or {}
    form = processed_payload.get("recent_form") or {}
    period_insights = processed_payload.get("period_insights") or []
    session_coach = processed_payload.get("session_coach")

    focus = analyze_focus_areas(summary, map_stats, mech, matches, impact)
    focus_list = focus.get("areas") or []

    sections = {
        "home": analyze_home(profile, summary, form, matches, mech, focus_list, session_coach, impact),
        "dashboard": analyze_dashboard(nickname, profile, summary, map_stats, mech, impact),
        "matches": analyze_matches(matches, mechanics_lab, summary, map_stats, mech),
        "sessions": analyze_sessions(matches, impact),
        "general": analyze_general(profile, summary, form, matches, period_insights, mech),
        "focus_areas": focus,
        "maps": analyze_maps(map_stats, matches, mechanics_lab),
        "aim": analyze_aim(mech),
        "utility": analyze_utility(mechanics_lab, demo_folder),
        "training": analyze_training(focus_list, map_stats, mech),
        "achievements": analyze_achievements(summary, map_stats, matches, mech, memory),
        "benchmarks": analyze_benchmarks(profile, summary, map_stats, mech, memory, impact),
        "operation": analyze_operation(mechanics_lab, mech, map_stats),
        "data_library": analyze_data_library(nickname, memory),
        "ask_ai": {
            "export_path": f"data/ai_exports/{nickname.lower()}_tara_latest.md",
        },
    }

    return {
        "nickname": nickname,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
    }


RENDERERS = {
    "home": render_home_markdown,
    "dashboard": render_dashboard_markdown,
    "matches": render_matches_markdown,
    "sessions": render_sessions_markdown,
    "general": render_general_markdown,
    "focus_areas": render_focus_areas_markdown,
    "maps": render_maps_markdown,
    "aim": render_aim_markdown,
    "utility": render_utility_markdown,
    "training": render_training_markdown,
    "achievements": render_achievements_markdown,
    "benchmarks": render_benchmarks_markdown,
    "operation": render_operation_markdown,
    "data_library": render_data_library_markdown,
    "ask_ai": render_ask_ai_markdown,
}

SECTION_ORDER = [
    "home", "dashboard", "matches", "sessions", "general", "focus_areas",
    "maps", "aim", "utility", "training", "achievements", "benchmarks",
    "operation", "data_library", "ask_ai",
]


def render_suite_markdown(suite: dict[str, Any]) -> str:
    nickname = suite.get("nickname", "Player")
    lines = [
        f"# {nickname} — Coach Analytics Suite",
        "",
        f"_Generated: {suite.get('generated_at', '')}_",
        "",
        "_Kaynak etiketleri: FACEIT API | Uploaded Demo | Derived / Estimated | Unavailable_",
        "",
    ]
    sections = suite.get("sections") or {}
    for key in SECTION_ORDER:
        renderer = RENDERERS.get(key)
        section = sections.get(key)
        if renderer and section:
            lines.extend(renderer(section))
    return "\n".join(lines)


def write_suite_report(
    nickname: str,
    suite: dict[str, Any],
    reports_dir: Path,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{nickname.lower()}_suite_latest.md"
    path.write_text(render_suite_markdown(suite), encoding="utf-8")
    return path
