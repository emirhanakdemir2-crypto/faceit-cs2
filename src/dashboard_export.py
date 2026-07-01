from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.suite_common import fmt_simple, metric_val


def _esc(val: Any) -> str:
    return html.escape(fmt_simple(val))


def render_dashboard_html(suite: dict[str, Any]) -> str:
    nickname = suite.get("nickname", "Player")
    sections = suite.get("sections") or {}
    home = sections.get("home") or {}
    dash = sections.get("dashboard") or {}
    focus = sections.get("focus_areas") or {}
    bench = sections.get("benchmarks") or {}

    focus_rows = ""
    for i, area in enumerate(focus.get("areas") or [], 1):
        focus_rows += f"""
        <div class="card">
          <h3>{i}. {_esc(area.get('title'))}</h3>
          <p>{_esc(area.get('metric_name'))}: {_esc(area.get('metric'))}</p>
          <p class="dim">Target: {_esc(area.get('target'))}</p>
          <p class="dim">Drill: {_esc(area.get('drill'))}</p>
        </div>"""

    bench_rows = ""
    for row in bench.get("rows") or []:
        verdict = fmt_simple(row.get("verdict"))
        cls = "good" if "above" in verdict else ("warn" if "near" in verdict else "bad")
        bench_rows += f"""
        <tr>
          <td>{_esc(row.get('metric'))}</td>
          <td>{_esc(row.get('current'))}</td>
          <td>{_esc(row.get('level10_target'))}</td>
          <td class="{cls}">{_esc(verdict)}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(nickname)} — Coach Dashboard</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a2332; --text:#e8eef5; --dim:#8b9cb3; --accent:#3d8bfd;
    --good:#3dd68c; --warn:#f5c542; --bad:#f56565; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:Segoe UI,system-ui,sans-serif; background:var(--bg); color:var(--text);
    line-height:1.5; padding:24px; }}
  h1 {{ margin:0 0 8px; font-size:1.6rem; }}
  h2 {{ margin:32px 0 12px; font-size:1.1rem; color:var(--accent); border-bottom:1px solid #2a3544; padding-bottom:6px; }}
  h3 {{ margin:0 0 8px; font-size:1rem; }}
  .sub {{ color:var(--dim); margin-bottom:24px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; }}
  .card {{ background:var(--card); border-radius:10px; padding:16px; border:1px solid #2a3544; }}
  .card .label {{ color:var(--dim); font-size:0.8rem; }}
  .card .value {{ font-size:1.4rem; font-weight:700; margin-top:4px; }}
  .dim {{ color:var(--dim); font-size:0.9rem; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border-radius:10px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #2a3544; }}
  th {{ color:var(--dim); font-weight:600; font-size:0.85rem; }}
  .good {{ color:var(--good); }}
  .warn {{ color:var(--warn); }}
  .bad {{ color:var(--bad); }}
  .commentary li {{ margin:4px 0; }}
</style>
</head>
<body>
  <h1>{_esc(nickname)} — Coach Analytics Dashboard</h1>
  <p class="sub">Jurses CS2 Coach Analytics Suite · {_esc(suite.get('generated_at',''))}</p>

  <h2>Home</h2>
  <div class="grid">
    <div class="card"><div class="label">Level</div><div class="value">{_esc(home.get('level'))}</div></div>
    <div class="card"><div class="label">ELO</div><div class="value">{_esc(home.get('elo'))}</div></div>
    <div class="card"><div class="label">Winrate</div><div class="value">{_esc(home.get('winrate'))}%</div></div>
    <div class="card"><div class="label">K/D</div><div class="value">{_esc(home.get('kd'))}</div></div>
    <div class="card"><div class="label">ADR</div><div class="value">{_esc(home.get('adr'))}</div></div>
    <div class="card"><div class="label">FACEIT Risk</div><div class="value">{_esc(home.get('faceit_risk'))}</div></div>
    <div class="card"><div class="label">Coach Rating</div><div class="value">{_esc(dash.get('coach_rating'))}</div></div>
    <div class="card"><div class="label">Aim Discipline</div><div class="value">{_esc(dash.get('aim_discipline'))}</div></div>
    <div class="card"><div class="label">Impact Rating</div><div class="value">{_esc(dash.get('impact_rating'))}</div></div>
    <div class="card"><div class="label">Impact Warning</div><div class="value">{_esc(dash.get('impact_warning'))}</div></div>
  </div>
  <ul class="commentary">
    {''.join(f'<li>{_esc(n)}</li>' for n in (home.get('commentary') or []))}
  </ul>

  <h2>Focus Areas</h2>
  <div class="grid">{focus_rows or '<p class="dim">No focus areas flagged.</p>'}</div>

  <h2>Benchmarks</h2>
  <table>
    <thead><tr><th>Metric</th><th>Current</th><th>L10 Target</th><th>Verdict</th></tr></thead>
    <tbody>{bench_rows}</tbody>
  </table>
</body>
</html>"""


def write_dashboard_html(
    suite: dict[str, Any],
    reports_dir: Path,
    nickname: str,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{nickname.lower()}_dashboard_latest.html"
    path.write_text(render_dashboard_html(suite), encoding="utf-8")
    return path
