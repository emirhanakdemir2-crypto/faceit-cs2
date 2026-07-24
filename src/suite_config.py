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

# Impact / Death Quality thresholds
OPENING_DUEL_GOOD = 55
OPENING_DUEL_OKAY = 45
OPENING_DUEL_WEAK = 45

UNTRADED_DEATH_GOOD = 35
UNTRADED_DEATH_OKAY = 50
UNTRADED_DEATH_WEAK = 50

EARLY_DEATH_GOOD = 15
EARLY_DEATH_OKAY = 25
EARLY_DEATH_WEAK = 25

POST_KILL_SURVIVAL_GOOD = 80
POST_KILL_SURVIVAL_OKAY = 65
POST_KILL_SURVIVAL_WEAK = 65

IMPACT_RATING_GOOD = 70
IMPACT_RATING_OKAY = 50
IMPACT_RATING_WEAK = 50

TARGET_UNTRADED_DEATH_PCT = 35
TARGET_EARLY_DEATH_PCT = 15
TARGET_POST_KILL_SURVIVAL_5S = 80

# Proper Counter-Strafe V2 (central thresholds — do not scatter)
V2_PROPER_SPEED_RATIO_MAX = 0.34
V2_CONFIDENCE_HIGH_MIN_ELIGIBLE = 80
V2_CONFIDENCE_MEDIUM_MIN_ELIGIBLE = 30
V2_CONFIDENCE_LOW_MIN_ELIGIBLE = 10
V2_TICK_MATCH_TOLERANCE = 8
V2_METRIC_LABEL = "proper_counter_strafe_v2"
V2_LEGACY_METRIC_LABEL = "legacy_first_bullet_moving"
V2_ELIGIBILITY_SOURCE_APPROX_SPOTTED = "approximate_spotted_mask"
V2_ELIGIBILITY_SOURCE_HURT = "player_hurt_same_tick"
V2_STATUS_EXPERIMENTAL = "experimental"
V2_STATUS_UNAVAILABLE = "Unavailable"
V2_MEASUREMENT_QUALITY_EXPERIMENTAL = "experimental"
V2_MEASUREMENT_QUALITY_VALIDATED = "validated"
V2_EVIDENCE_SPOTTED_ONLY = "spotted_only"
V2_EVIDENCE_SPOTTED_AND_HURT = "spotted_and_hurt"
V2_EVIDENCE_HURT_ONLY = "hurt_only"
V2_EVIDENCE_UNRESOLVED = "unresolved"
V2_HEADLINE_EVIDENCE_BUCKETS = (V2_EVIDENCE_SPOTTED_ONLY, V2_EVIDENCE_SPOTTED_AND_HURT)
V2_DISPLAY_TITLE = "Proper Counter-Strafe V2 (Experimental — approximate spotted data)"
V2_COACH_SOFT_LABEL = "güçlü counter-strafe adayı"

# Geometry Visibility / LoS V1 (diagnostic only — never promotes V2 to validated)
GEOMETRY_BACKEND_SOURCE = "awpy.VisibilityChecker"
GEOMETRY_BACKEND_VERSION_PIN = "2.0.2"
GEOMETRY_MEASUREMENT_QUALITY = "experimental_geometry_v1"
GEOMETRY_STATUS_DEPENDENCY_MISSING = "dependency_missing"
GEOMETRY_STATUS_TRI_MISSING = "tri_missing"
GEOMETRY_STATUS_UNSUPPORTED_MAP = "unsupported_map"
GEOMETRY_STATUS_INIT_FAILED = "init_failed"
GEOMETRY_STATUS_AVAILABLE = "available"
GEOMETRY_SETUP_COMMAND = "python -m pip install awpy==2.0.2 && awpy get tris"
# Approximate eye height (Source units) — not demo-derived eye offset.
GEOMETRY_APPROX_EYE_HEIGHT_STANDING = 64.0
GEOMETRY_APPROX_EYE_HEIGHT_CROUCHED = 46.0
GEOMETRY_EYE_HEIGHT_SOURCE = "config_approximate_eye_height_v1"
# Demo fov field observed as always 0; use config approximate FOV for candidate filter.
GEOMETRY_APPROX_HORIZONTAL_FOV_DEG = 90.0
GEOMETRY_FOV_SOURCE = "config_approximate_horizontal_fov_v1"
GEOMETRY_QUALITY_APPROXIMATE = "geometry_approximate"
GEOMETRY_AGREEMENT_VISIBLE_SPOTTED = "geometry_visible_and_spotted"
GEOMETRY_AGREEMENT_VISIBLE_NOT_SPOTTED = "geometry_visible_not_spotted"
GEOMETRY_AGREEMENT_BLOCKED_SPOTTED = "geometry_blocked_and_spotted"
GEOMETRY_AGREEMENT_BLOCKED_NOT_SPOTTED = "geometry_blocked_not_spotted"
