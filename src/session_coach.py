from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import MISSING_DATA_LABEL
from src.metrics import (
    _mean_or_missing,
    _numeric_series,
    compute_map_stats,
    compute_recent_form,
)


def _float(val: Any) -> float | None:
    if val in (None, "", MISSING_DATA_LABEL):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compute_map_stats_from_matches(matches: list[dict[str, Any]]) -> dict[str, Any]:
    return compute_map_stats({"matches": matches})


def _streak_counts(recent: list[dict[str, Any]]) -> dict[str, int]:
    current_loss = 0
    current_win = 0
    max_loss = 0
    max_win = 0

    for m in recent:
        if m.get("won") is True:
            current_win += 1
            current_loss = 0
        elif m.get("won") is False:
            current_loss += 1
            current_win = 0
        else:
            break

    run_l = run_w = 0
    for m in recent:
        if m.get("won") is False:
            run_l += 1
            run_w = 0
            max_loss = max(max_loss, run_l)
        elif m.get("won") is True:
            run_w += 1
            run_l = 0
            max_win = max(max_win, run_w)
        else:
            run_l = run_w = 0

    return {
        "current_loss_streak": current_loss,
        "current_win_streak": current_win,
        "max_loss_streak": max_loss,
        "max_win_streak": max_win,
    }


def _consecutive_map_losses_from_start(recent: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """En yeni maçtan geriye aynı haritada üst üste loss."""
    if not recent:
        return []
    streak_map: str | None = None
    streak_len = 0
    for m in recent:
        if m.get("won") is not False:
            break
        mp = m.get("map")
        if not mp or mp == MISSING_DATA_LABEL:
            break
        if streak_map is None:
            streak_map = mp
            streak_len = 1
        elif mp == streak_map:
            streak_len += 1
        else:
            break
    if streak_map and streak_len >= 2:
        return [(streak_map, streak_len)]
    return []


def _map_distribution(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for m in matches:
        mp = m.get("map")
        if mp and mp != MISSING_DATA_LABEL:
            counts[mp] = counts.get(mp, 0) + 1
    return [{"map": k, "played": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]


def _high_adr_losses(matches: list[dict[str, Any]], threshold: float = 75.0) -> list[str]:
    rows: list[str] = []
    for m in matches:
        if m.get("won") is not False:
            continue
        adr = _float(m.get("adr"))
        if adr is not None and adr >= threshold:
            rows.append(
                f"{m.get('map')} — ADR {adr}, K/D {m.get('kd_ratio')} ({m.get('finished_at')})"
            )
    return rows


def compute_extended_recent_form(
    matches: list[dict[str, Any]],
    count: int = 10,
) -> dict[str, Any]:
    """Son N maç için session coach form özeti."""
    recent = matches[:count]
    base = compute_recent_form({"matches": matches}, count=count)
    with_stats = [m for m in recent if m.get("stats_available")]
    hs = _numeric_series(with_stats, "headshot_pct")
    base["avg_headshot_pct"] = _mean_or_missing(hs)
    base["map_distribution"] = _map_distribution(recent)
    base["map_stats"] = compute_map_stats_from_matches(recent)
    base.update(_streak_counts(recent))
    base["high_adr_losses"] = _high_adr_losses(recent)
    base["consecutive_map_losses"] = _consecutive_map_losses_from_start(recent)
    return base


def compare_recent_to_baseline(
    baseline_summary: dict[str, Any],
    baseline_map_stats: dict[str, Any],
    recent_form: dict[str, Any],
    recent_count: int,
) -> dict[str, Any]:
    """90 gün baseline ile son N maç kıyaslaması."""
    comparisons: list[dict[str, Any]] = []
    commentary: list[str] = []

    pairs = [
        ("Win rate", "win_rate_pct", "%"),
        ("K/D", "avg_kd_ratio", ""),
        ("ADR", "avg_adr", ""),
        ("Headshot %", "avg_headshot_pct", "%"),
    ]

    for label, key, _suffix in pairs:
        b = _float(baseline_summary.get(key))
        r = _float(recent_form.get(key))
        if b is None or r is None:
            comparisons.append({
                "metric": label,
                "baseline": baseline_summary.get(key, MISSING_DATA_LABEL),
                "recent": recent_form.get(key, MISSING_DATA_LABEL),
                "delta": MISSING_DATA_LABEL,
            })
            continue
        comparisons.append({
            "metric": label,
            "baseline": b,
            "recent": r,
            "delta": round(r - b, 2),
        })

    b_wr = _float(baseline_summary.get("win_rate_pct"))
    r_wr = _float(recent_form.get("win_rate_pct"))
    b_kd = _float(baseline_summary.get("avg_kd_ratio"))
    r_kd = _float(recent_form.get("avg_kd_ratio"))
    b_adr = _float(baseline_summary.get("avg_adr"))
    r_adr = _float(recent_form.get("avg_adr"))

    if (
        r_adr is not None and b_adr is not None and r_adr >= b_adr
        and r_wr is not None and b_wr is not None and r_wr < b_wr - 3
    ):
        commentary.append("Hasar round kazanımına dönüşmüyor.")

    if r_kd is not None and b_kd is not None and r_kd >= b_kd and r_wr is not None and r_wr < 50:
        commentary.append("Impact veya takım/round kararları incelenmeli.")

    if b_wr is not None and r_wr is not None and r_wr <= b_wr - 10:
        commentary.append("Güncel form düşüşü.")

    if (
        r_kd is not None and b_kd is not None and r_kd > b_kd
        and r_wr is not None and b_wr is not None and r_wr < b_wr - 5
    ):
        commentary.append("Bireysel temas iyi, round kapatma/impact sorunu olabilir.")

    for mp, streak_len in recent_form.get("consecutive_map_losses") or []:
        commentary.append(f"{mp}: Bu haritada queue riski var. ({streak_len} üst üste loss)")

    loss_streak = recent_form.get("current_loss_streak", 0)
    if loss_streak >= 3:
        commentary.append("Bugün FACEIT kapat öner.")
    elif loss_streak >= 2:
        commentary.append("Mola öner.")

    map_compare: list[str] = []
    baseline_maps = {r["map"]: r for r in baseline_map_stats.get("maps") or []}
    for row in recent_form.get("map_stats", {}).get("maps") or []:
        mp = row.get("map")
        if mp in baseline_maps:
            bwr = baseline_maps[mp].get("win_rate_pct")
            rwr = row.get("win_rate_pct")
            if bwr != MISSING_DATA_LABEL and rwr != MISSING_DATA_LABEL:
                map_compare.append(f"{mp}: son {recent_count} maç %{rwr} vs 90g %{bwr}")

    if not commentary:
        commentary.append("Son form baseline ile genel olarak uyumlu.")

    return {
        "recent_count": recent_count,
        "comparisons": comparisons,
        "commentary": commentary,
        "map_comparisons": map_compare,
    }


def compute_focus_risk_score(
    baseline_summary: dict[str, Any],
    recent_form: dict[str, Any],
    all_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    score = 0
    factors: list[str] = []

    recent_matches = all_matches[:10]
    if len(recent_matches) >= 5:
        last5 = recent_matches[:5]
        wins = sum(1 for m in last5 if m.get("won") is True)
        losses = sum(1 for m in last5 if m.get("won") is False)
        if wins + losses > 0:
            last5_wr = wins / (wins + losses) * 100
            if last5_wr < 40:
                score += 20
                factors.append("Son 5 maç win rate düşük (+20)")

    loss_streak = recent_form.get("current_loss_streak", 0)
    if loss_streak >= 2:
        score += 20
        factors.append(f"{loss_streak} loss streak (+20)")

    b_wr = _float(baseline_summary.get("win_rate_pct"))
    r_wr = _float(recent_form.get("win_rate_pct"))
    if b_wr is not None and r_wr is not None and r_wr < b_wr:
        score += 20
        factors.append("Son 10 win rate baseline altında (+20)")

    b_adr = _float(baseline_summary.get("avg_adr"))
    r_adr = _float(recent_form.get("avg_adr"))
    if (
        b_adr is not None and r_adr is not None and r_adr >= b_adr
        and r_wr is not None and b_wr is not None and r_wr < b_wr - 3
    ):
        score += 15
        factors.append("ADR iyi ama win düşük (+15)")

    if recent_form.get("consecutive_map_losses"):
        mp = recent_form["consecutive_map_losses"][0][0]
        score += 15
        factors.append(f"{mp} tekrar loss (+15)")

    b_kd = _float(baseline_summary.get("avg_kd_ratio"))
    r_kd = _float(recent_form.get("avg_kd_ratio"))
    if b_kd is not None and r_kd is not None and r_kd < b_kd - 0.05:
        score += 10
        factors.append("K/D baseline altında (+10)")

    score = min(100, score)

    if score <= 30:
        band = "Queue yapılabilir"
        queue_decision = "Bugün queue yapılabilir."
    elif score <= 60:
        band = "Dikkatli queue, maksimum 1-2 maç"
        queue_decision = "Maksimum 2 maç önerilir."
    elif score <= 80:
        band = "Önce mola/warmup/review"
        queue_decision = "Önce 15 dk warmup + 1 demo/klip review önerilir."
    else:
        band = "Bugün ciddi FACEIT önerilmez"
        queue_decision = "Bugün FACEIT kapatmak daha mantıklı."

    return {
        "score": score,
        "band": band,
        "factors": factors or ["Belirgin risk faktörü yok."],
        "queue_decision": queue_decision,
    }


def compute_next_match_focus(
    comparison: dict[str, Any],
    recent_form: dict[str, Any],
    risk: dict[str, Any],
) -> str:
    commentary = comparison.get("commentary") or []
    riskiest = recent_form.get("riskiest_map", "")
    high_adr_losses = recent_form.get("high_adr_losses") or []

    for line in commentary:
        if "round kazanımına dönüşmüyor" in line:
            for entry in high_adr_losses:
                if "dust2" in str(entry).lower():
                    return "Dust2'de yüksek ADR'i round impact'e çevir."
            return "Kill aldıktan sonra aynı açıda kalma."

    if risk.get("score", 0) >= 61:
        return "İlk 20 saniye gereksiz ölme."

    joined = " ".join(commentary).lower()
    if "impact" in joined or "round kararları" in joined:
        return "Trade mesafesinden kopma."

    if riskiest and riskiest != MISSING_DATA_LABEL and "inferno" in riskiest.lower():
        return "Inferno'da erken duel alma."

    if riskiest and riskiest != MISSING_DATA_LABEL:
        return f"{riskiest} için default pozisyonu koru, gereksiz peek alma."

    return "Round planı net: info → trade → site kontrolü."


def mental_toxicity_notes(risk: dict[str, Any]) -> list[str]:
    notes = [
        "Clutchta gereksiz konuşma varsa mute öner.",
        "2. toksik yorumdan sonra mute öner.",
        "“Pardon” deyip gereksiz suçu üstlenme; net call kullan:",
        '- "Clutch, sadece info."',
        '- "B lurk tuttum, bırakamazdım."',
        '- "Rounddan sonra bakarız."',
        '- "Şu an tartışmayacağım, oynayalım."',
    ]
    if risk.get("score", 0) >= 61:
        notes.insert(0, "Yüksek risk skoru — tilt/toxicity tetikleyicilerine ekstra dikkat.")
    return notes


def build_session_coach(
    all_matches: list[dict[str, Any]],
    baseline_summary: dict[str, Any],
    baseline_map_stats: dict[str, Any],
    *,
    recent_count: int = 10,
    days: int = 90,
) -> dict[str, Any]:
    recent_form = compute_extended_recent_form(all_matches, count=recent_count)
    comparison = compare_recent_to_baseline(
        baseline_summary, baseline_map_stats, recent_form, recent_count,
    )
    risk = compute_focus_risk_score(baseline_summary, recent_form, all_matches)
    next_focus = compute_next_match_focus(comparison, recent_form, risk)
    mental = mental_toxicity_notes(risk)

    return {
        "days": days,
        "recent_count": recent_count,
        "baseline_summary": baseline_summary,
        "baseline_map_stats": baseline_map_stats,
        "recent_form": recent_form,
        "comparison": comparison,
        "focus_risk": risk,
        "next_match_focus": next_focus,
        "mental_notes": mental,
    }


def write_clip_review_template(path: Path, nickname: str) -> Path:
    content = f"""# Clip Review Template — {nickname}

Maç sonrası 1 round veya kritik death için doldur.

| Alan | Not |
| --- | --- |
| Harita | |
| Taraf | CT / T |
| Round | |
| Skor | |
| Demo dosyası | |
| Tick/zaman | |
| Klip linki | |
| Ben ne yapmaya çalıştım? | |
| Takım bana ne dedi? | |
| Pozisyon kararı doğru muydu? | Evet / Hayır — neden? |
| Ölüm sebebi | |
| Alternatif daha iyi karar | |
| Bir sonraki maçta uygulanacak ders | |

---
*Session Coach — faceit-cs2-coach*
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def load_cached_baseline(
    nickname: str,
    processed_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    path = processed_dir / f"{nickname.lower()}_summary.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data.get("summary")
        map_stats = data.get("map_stats")
        if summary and map_stats:
            return summary, map_stats
    except (OSError, json.JSONDecodeError):
        return None
    return None
