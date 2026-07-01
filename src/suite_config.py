"""Coach Analytics Suite — eşik değerleri ve hedefler."""

from __future__ import annotations

# Level 10 gap / benchmark hedefleri
TARGET_KD = 1.15
TARGET_ADR = 82.0
TARGET_WINRATE = 52.0
TARGET_HS_PCT = 50.0

# Mechanics — düşük = iyi
TARGET_RIFLE_FIRST_BULLET_MOVING = 45.0
TARGET_RIFLE_LONG_SPRAY = 30.0
TARGET_STARTER_PISTOL_FIRST_BULLET = 55.0
TARGET_AK_FIRST_BULLET = 50.0
TARGET_M4_LONG_SPRAY = 40.0

# Focus area tetikleyicileri — yüksek = sorun
FOCUS_RIFLE_FIRST_BULLET = 60.0
FOCUS_AK_FIRST_BULLET = 60.0
FOCUS_M4_LONG_SPRAY = 40.0
FOCUS_STARTER_PISTOL_FIRST = 60.0
FOCUS_WEAK_MAP_WR = 45.0

# Harita örneklem
MAP_VERY_LOW_MAX = 2
MAP_LOW_MIN = 3
MAP_LOW_MAX = 9
MAP_USABLE_MIN = 10

# Session
SESSION_GAP_HOURS = 3
SESSION_TILT_MATCHES = 3

# Coach Rating ağırlıkları (0–100 bileşenleri)
COACH_RATING_WEIGHTS = {
    "kd": 0.22,
    "adr": 0.18,
    "winrate": 0.18,
    "mechanics": 0.22,
    "map_pool": 0.10,
    "consistency": 0.10,
}

LEVEL_10_TARGET_LEVEL = 10
