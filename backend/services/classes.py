"""Load military_classes.yaml (238 UI names). Map YOLO indices 0-11 by YAML id.

Sprint 2: SQLite class_overrides merge into catalog, aliases, YOLOE prompts.
"""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from config import BASE_DIR

YAML_PATH = BASE_DIR / "military_classes.yaml"
MODEL_NC = 12

_catalog: list[dict[str, Any]] | None = None
_by_id: dict[int, dict[str, Any]] | None = None
_alias_map: dict[str, str] | None = None  # alias lower → name_raw
_disabled_ids: set[int] | None = None
_excluded_cache: set[str] | None = None  # dynamic excluded classes cache


def to_snake_case(name: str) -> str:
    """Convert YAML labels ('tank turret in ground') to frontend snake_case."""
    text = name.strip().lower().replace("-", " ").replace("/", " ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def invalidate_class_cache() -> None:
    """Drop in-memory catalog after SYSTEM dictionary edits."""
    global _catalog, _by_id, _alias_map, _disabled_ids, _excluded_cache
    _catalog = None
    _by_id = None
    _alias_map = None
    _disabled_ids = None
    _excluded_cache = None
    canonical_label.cache_clear()


def _load_yaml() -> dict[int, str]:
    if not YAML_PATH.exists():
        print(f"[CLASSES] YAML not found at {YAML_PATH}")
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required: pip install PyYAML") from exc

    data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    names = data.get("names", data)
    if isinstance(names, dict):
        return {int(k): str(v) for k, v in names.items()}
    if isinstance(names, list):
        return {i: str(v) for i, v in enumerate(names)}
    return {}


def _load_overrides() -> list[dict[str, Any]]:
    try:
        from services.db import list_class_overrides

        return list_class_overrides()
    except Exception as exc:  # noqa: BLE001
        print(f"[CLASSES] overrides unavailable: {exc}")
        return []


def get_class_catalog() -> list[dict[str, Any]]:
    """238 UI classes keyed by YAML index. Merges SQLite overrides."""
    global _catalog, _by_id, _alias_map, _disabled_ids
    if _catalog is not None:
        return _catalog

    raw = _load_yaml()
    overrides = {int(o["class_id"]): o for o in _load_overrides()}
    catalog: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    alias_map: dict[str, str] = {}
    disabled: set[int] = set()

    for class_id in sorted(raw):
        raw_name = raw[class_id]
        snake = to_snake_case(raw_name)
        ov = overrides.get(class_id)
        enabled = True if ov is None else bool(ov.get("enabled", True))
        name_ru = str(ov.get("name_ru") or "") if ov else ""
        in_prompt = bool(ov.get("in_prompt")) if ov else False
        confidence_threshold = (
            float(ov["confidence_threshold"])
            if ov and ov.get("confidence_threshold") is not None
            else None
        )
        aliases: list[str] = []
        if ov:
            try:
                parsed = json.loads(ov.get("aliases") or "[]")
                if isinstance(parsed, list):
                    aliases = [str(a) for a in parsed]
            except Exception:  # noqa: BLE001
                aliases = []
        for alias in aliases:
            key = alias.strip().lower().replace("_", " ")
            if key:
                alias_map[key] = raw_name
        if not enabled:
            disabled.add(class_id)
        item = {
            "id": class_id,
            "name_raw": raw_name,
            "name_en": snake,
            "name_ru": name_ru,
            "aliases": aliases,
            "enabled": enabled,
            "in_prompt": in_prompt,
            "confidence_threshold": confidence_threshold,
            "is_model_class": True,
            "has_override": ov is not None,
        }
        catalog.append(item)
        by_id[class_id] = item

    _catalog = catalog
    _by_id = by_id
    _alias_map = alias_map
    _disabled_ids = disabled
    print(
        f"[CLASSES] Loaded {len(catalog)} UI classes "
        f"({len(overrides)} overrides, {len(disabled)} disabled)"
    )
    return catalog


def ui_name_by_index(class_id: int) -> str:
    """Model index N → YAML index N → snake_case UI name."""
    get_class_catalog()
    item = (_by_id or {}).get(int(class_id))
    if item:
        return str(item["name_en"])
    return f"class_{int(class_id)}"


def model_ui_names() -> list[str]:
    """First 12 YAML names (indices 0-11) for a 12-class YOLO26 head."""
    get_class_catalog()
    names = [f"class_{i}" for i in range(MODEL_NC)]
    for item in get_class_catalog():
        idx = int(item["id"])
        if 0 <= idx < MODEL_NC:
            names[idx] = str(item["name_en"])
    return names


def get_ui_names() -> list[str]:
    return [str(item["name_en"]) for item in get_class_catalog() if item.get("enabled", True)]


def confidence_threshold_for(name: str) -> float | None:
    """Return an operator override for a canonical class name, if configured."""
    wanted = to_snake_case(name)
    for item in get_class_catalog():
        if str(item.get("name_en") or "") == wanted:
            value = item.get("confidence_threshold")
            return float(value) if value is not None else None
    return None


def minimum_confidence_threshold() -> float | None:
    values = [
        float(item["confidence_threshold"])
        for item in get_class_catalog()
        if item.get("enabled", True) and item.get("confidence_threshold") is not None
    ]
    return min(values) if values else None


# True background / frame-swallowers only — NOT LBS engineering features.
# trench / foxhole / barbed wire / footpaths / craters must stay detectable.
_SCENE_EXACT = {
    "trampled vegetation",
    "tree line",
    "forest edge",
    "open field",
    "bridge",
    "river",
    "lake",
    "building",
    "ruin",
    "smoke",
    "dust cloud",
    "shadow",
}

_SCENE_SUBSTR = (
    "terrain",
    "vegetation",
    "landscape",
    "background",
    "road surface",
)

_PRIORITY_TOKENS = (
    "soldier",
    "person",
    "drone",
    "uav",
    "tank",
    "armor",
    "vehicle",
    "truck",
    "jeep",
    "helicopter",
    "aircraft",
    "armored",
    "trench",
    "foxhole",
    "barbed",
    "crater",
    "wreck",
)

_CLUTTER_SUBSTR = (
    "plastic bottle",
    "food wrapper",
    "discarded paper",
    "cigarette",
    "litter pile",
    "food can",
    "cardboard box",
    "plastic bag",
    "garbage pile",
)


def _prompt_rank(name: str) -> int:
    blob = (name or "").lower().replace("_", " ")
    if any(tok in blob for tok in ("drone", "uav", "quadcopter", "fpv", "mine", "booby", "tripwire")):
        return 0
    if any(tok in blob for tok in _PRIORITY_TOKENS):
        return 1
    return 2


def is_scene_class(name: str) -> bool:
    blob = (name or "").strip().lower().replace("_", " ")
    if blob in _SCENE_EXACT:
        return True
    return any(tok in blob for tok in _SCENE_SUBSTR)


def is_clutter_class(name: str) -> bool:
    blob = (name or "").lower().replace("_", " ")
    return any(tok in blob for tok in _CLUTTER_SUBSTR)


def yaml_prompt_names() -> list[str]:
    """Tactical YAML prompts: drones/mines first, no terrain or litter."""
    items = [
        str(item["name_raw"])
        for item in get_class_catalog()
        if item.get("enabled", True)
        and not is_scene_class(str(item["name_raw"]))
        and not is_clutter_class(str(item["name_raw"]))
    ]
    items.sort(key=_prompt_rank)
    return items


# CLIP open-vocab degrades with 100+ prompts. Keep a short live list.
# "person" is not in YAML; it is the CLIP word that matches aerial people.
_LIVE_PROMPT_RAW = (
    "person",
    "soldier",
    "armed person",
    "person in camouflage uniform",
    "person carrying rifle",
    "soldier in civilian clothing",
    "group of soldiers",
    "running soldier",
    "quadcopter drone",
    "FPV drone",
    "fixed-wing drone",
    "reconnaissance drone",
    "tank",
    "armored vehicle",
    "armored personnel carrier",
    "military truck",
    "military jeep",
    "military helicopter",
    "military aircraft",
    "howitzer",
    "self-propelled artillery",
    # LBS / fortification cues (aerial)
    "trench",
    "foxhole",
    "barbed wire",
    "barbed wire coil",
    "shell crater with scorched earth",
    "anti-tank ditch",
    "anti-tank obstacle",
    "footpath in grass",
    "narrow footpath through bushes",
    "tire track",
    "drone wreckage",
    # anomalies / litter / fresh earth (LBS reconnaissance)
    "plastic bottle",
    "metal can",
    "food can",
    "food wrapper",
    "plastic bag",
    "litter pile",
    "garbage pile",
    "disturbed soil",
    "fresh dug dirt",
    "freshly dug soil patch",
    "spoil heap of dug-out soil",
    "shell crater with scorched earth",
)

_LABEL_ALIASES = {
    "person": "soldier",
    "people": "group of soldiers",
    "human": "soldier",
    "pedestrian": "soldier",
    # kite/bird → soldier removed: false positives on UAV footage (Sprint 1).
    # "kite": "soldier",
    # "bird": "soldier",
    "car": "military truck",
    "truck": "military truck",
    "bus": "military truck",
    "airplane": "military aircraft",
    "helicopter": "military helicopter",
    "motorcycle": "military jeep",
    # LBS / wreck cues from open-vocab / COCO-ish labels
    "burned armored vehicle": "armored vehicle",
    "destroyed tank": "tank",
    "vehicle wreck": "armored vehicle",
    "wreck": "armored vehicle",
    "burned vehicle": "armored vehicle",
    "destroyed vehicle": "armored vehicle",
    "crater": "shell crater with scorched earth",
    "shell crater": "shell crater with scorched earth",
    "scorched earth": "shell crater with scorched earth",
    "dirt road": "tire track",
    "road": "tire track",
    "path": "footpath in grass",
}


@functools.lru_cache(maxsize=512)
def canonical_label(name: str) -> str:
    """Map CLIP/COCO synonyms onto YAML raw names (overrides → static aliases)."""
    get_class_catalog()
    raw = (name or "").strip().lower().replace("_", " ")
    if _alias_map and raw in _alias_map:
        return _alias_map[raw]
    return _LABEL_ALIASES.get(raw, (name or "").strip())


def get_excluded_classes() -> set[str]:
    """Return set of excluded class names (lowercase, underscored).
    
    Cached for performance; call invalidate_excluded_cache() after
    INSERT/DELETE on excluded_classes table.
    """
    global _excluded_cache
    if _excluded_cache is not None:
        return _excluded_cache
    
    excluded: set[str] = set()
    try:
        from services.db import list_excluded_classes
        for row in list_excluded_classes():
            excluded.add(row["class_name"].lower().replace(" ", "_"))
    except Exception:
        pass
    
    _excluded_cache = excluded
    return excluded


def invalidate_excluded_cache() -> None:
    """Call after INSERT/DELETE on excluded_classes table."""
    global _excluded_cache
    _excluded_cache = None


def is_catalog_label(name: str) -> bool:
    """True if name resolves to an enabled catalog entry."""
    cid = class_id_for_name(name)
    if cid < 0:
        return False
    get_class_catalog()
    if _disabled_ids and cid in _disabled_ids:
        return False
    return True


def live_prompt_names() -> list[str]:
    """Short YOLOE text list + SYSTEM in_prompt overrides."""
    catalog = get_class_catalog()
    catalog_raw = {
        str(item["name_raw"]).strip().lower()
        for item in catalog
        if item.get("enabled", True)
    }
    out: list[str] = []
    seen: set[str] = set()
    for raw in _LIVE_PROMPT_RAW:
        key = raw.strip().lower()
        if key in seen:
            continue
        if key != "person" and key not in catalog_raw:
            continue
        seen.add(key)
        out.append(raw)
    # Engineer-marked prompts from dictionary
    for item in catalog:
        if not item.get("enabled", True) or not item.get("in_prompt"):
            continue
        raw = str(item["name_raw"]).strip()
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
        for alias in item.get("aliases") or []:
            a = str(alias).strip()
            ak = a.lower()
            if a and ak not in seen:
                seen.add(ak)
                out.append(a)
    return out or yaml_prompt_names()[:24]


def class_id_for_name(name: str) -> int:
    """Map a model/prompt label to YAML index via snake_case."""
    get_class_catalog()
    mapped = canonical_label(name)
    snake = to_snake_case(mapped)
    for item in get_class_catalog():
        if str(item["name_en"]) == snake:
            return int(item["id"])
        if str(item["name_raw"]).strip().lower() == mapped.strip().lower():
            return int(item["id"])
    return -1


def validate_model_nc(nc: int) -> None:
    """Import rule: nc must be 12 (current best.pt) or 238 (full UI dictionary)."""
    if nc not in (12, 238):
        raise ValueError(f"Unsupported model.nc={nc}; expected 12 or 238")
