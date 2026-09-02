"""KML / GeoJSON export for geotagged detections.

Hand-builds KML 2.2 (XML via xml.etree.ElementTree, safe escaping/UTF-8) and
GeoJSON (FeatureCollection) without external geo libs (air-gap friendly).
GPS comes from detections.gps_lat/gps_lon/gps_alt; missing GPS is interpolated
from flight_tracks via services.telemetry. Detections without GPS are skipped
(cannot be placed on a map).

Class colors: deterministic palette (hash of class name -> hex), seeded from
the frontend Timeline palette so exports are stable across runs.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from services import telemetry
from services.db import list_detections

# Seed palette (mirrors src/components/Timeline.tsx class colors).
_SEED_PALETTE = [
    "#ef4444", "#3b82f6", "#f59e0b", "#10b981", "#a855f7",
    "#ec4899", "#14b8a6", "#f97316", "#84cc16", "#06b6d4",
]


def _class_color(class_name: str) -> str:
    """Deterministic hex color for a class name."""
    if not class_name:
        return "#64748b"
    h = hashlib.md5(class_name.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(_SEED_PALETTE)
    return _SEED_PALETTE[idx]


def _hex_to_kml_abgr(hex_color: str) -> str:
    """KML color is aabbggrr (alpha + BGR, reversed)."""
    c = hex_color.lstrip("#")
    if len(c) != 6:
        return "ff64748b"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"ff{b}{g}{r}"


def _style_id(class_name: str) -> str:
    """Stable Style id (Python hash() is randomized across processes)."""
    digest = hashlib.md5(class_name.encode("utf-8")).hexdigest()[:12]
    return f"style_{digest}"


def collect_geotagged_detections(video_path: str) -> list[dict[str, Any]]:
    """Return detections for a video that have GPS (enriched if missing)."""
    rows = list_detections(source_video=video_path, include_deleted=False)
    if not rows:
        base = Path(video_path).name
        all_rows = list_detections(include_deleted=False)
        rows = [r for r in all_rows if Path(str(r.get("source_video") or "")).name == base]

    track = telemetry.load_track_points(video_path)

    out: list[dict[str, Any]] = []
    for r in rows:
        det = dict(r)
        if det.get("gps_lat") is None or det.get("gps_lon") is None:
            pt = telemetry.interpolate(track, float(det.get("time_sec") or 0))
            if not pt:
                continue
            det["gps_lat"] = pt.get("lat")
            det["gps_lon"] = pt.get("lon")
            det["gps_alt"] = pt.get("alt")
        lat = det.get("gps_lat")
        lon = det.get("gps_lon")
        if lat is None or lon is None:
            continue
        try:
            float(lat)
            float(lon)
        except (TypeError, ValueError):
            continue
        out.append(det)
    return out


def build_kml(video_path: str, detections: list[dict[str, Any]] | None = None) -> str:
    """Build KML 2.2 XML string for geotagged detections of a video."""
    if detections is None:
        detections = collect_geotagged_detections(video_path)

    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    name = ET.SubElement(doc, "name")
    name.text = f"MuraveiVision — {Path(video_path).name}"
    desc = ET.SubElement(doc, "description")
    desc.text = f"{len(detections)} geotagged detections"

    # One Style per class (color).
    styles_seen: set[str] = set()
    for det in detections:
        cls = str(det.get("class_name") or det.get("class_id") or "unknown")
        if cls in styles_seen:
            continue
        styles_seen.add(cls)
        style = ET.SubElement(doc, "Style", id=_style_id(cls))
        icon = ET.SubElement(style, "IconStyle")
        color = ET.SubElement(icon, "color")
        color.text = _hex_to_kml_abgr(_class_color(cls))
        scale = ET.SubElement(icon, "scale")
        scale.text = "1.0"

    folder = ET.SubElement(doc, "Folder")
    fname = ET.SubElement(folder, "name")
    fname.text = Path(video_path).name

    for det in detections:
        cls = str(det.get("class_name") or det.get("class_id") or "unknown")
        lat = float(det["gps_lat"])
        lon = float(det["gps_lon"])
        alt = float(det.get("gps_alt") or 0)
        conf = det.get("confidence")
        time_sec = det.get("time_sec")
        pm = ET.SubElement(folder, "Placemark")
        ET.SubElement(pm, "name").text = cls
        ET.SubElement(
            pm, "description"
        ).text = (
            f"class={cls}\nconfidence={conf}\ntime_sec={time_sec}\n"
            f"source_video={det.get('source_video')}"
        )
        style_url = ET.SubElement(pm, "styleUrl")
        style_url.text = f"#{_style_id(cls)}"
        point = ET.SubElement(pm, "Point")
        coords = ET.SubElement(point, "coordinates")
        # KML coordinate order: lon,lat,alt
        coords.text = f"{lon},{lat},{alt}"
        if time_sec is not None:
            ts = ET.SubElement(pm, "TimeStamp")
            ET.SubElement(ts, "when").text = _time_to_iso(float(time_sec))

    return ET.tostring(kml, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _time_to_iso(time_sec: float) -> str:
    """Best-effort: emit seconds as a duration-ish timestamp. KML TimeStamp
    wants xsd:dateTime; without a real clock we emit epoch-based UTC."""
    import datetime as _dt

    epoch = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
    return (epoch + _dt.timedelta(seconds=float(time_sec))).isoformat()


def build_geojson(video_path: str, detections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection for geotagged detections of a video."""
    if detections is None:
        detections = collect_geotagged_detections(video_path)

    features: list[dict[str, Any]] = []
    for det in detections:
        lat = float(det["gps_lat"])
        lon = float(det["gps_lon"])
        alt = float(det.get("gps_alt") or 0)
        cls = str(det.get("class_name") or det.get("class_id") or "unknown")
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat, alt]},
                "properties": {
                    "class": cls,
                    "class_id": det.get("class_id"),
                    "confidence": det.get("confidence"),
                    "time_sec": det.get("time_sec"),
                    "source_video": det.get("source_video"),
                    "color": _class_color(cls),
                    "bbox": {
                        "x": det.get("bbox_x"),
                        "y": det.get("bbox_y"),
                        "w": det.get("bbox_w"),
                        "h": det.get("bbox_h"),
                    },
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}},
        "features": features,
    }


_CHANGE_COLORS = {
    "new": "#22c55e",
    "removed": "#ef4444",
    "moved": "#eab308",
}


def _gps_ok(lat: Any, lon: Any) -> bool:
    if lat is None or lon is None:
        return False
    try:
        float(lat)
        float(lon)
        return not (float(lat) == 0.0 and float(lon) == 0.0)
    except (TypeError, ValueError):
        return False


def build_change_kml(result: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    """KML for change-detection report: folders New / Removed / Moved.

    Items without GPS are skipped. Empty report still returns valid Document.
    """
    meta = meta or {}
    stamp = str(meta.get("generated_at") or "")
    title = f"Change Detection Report - {stamp}" if stamp else "Change Detection Report"

    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = title
    summary = result.get("summary") or {}
    ET.SubElement(doc, "description").text = (
        f"before={meta.get('video_before')} after={meta.get('video_after')} "
        f"new={summary.get('new', 0)} removed={summary.get('removed', 0)} "
        f"moved={summary.get('moved', 0)}"
    )

    for kind, hex_color in _CHANGE_COLORS.items():
        style = ET.SubElement(doc, "Style", id=f"chg_{kind}")
        icon = ET.SubElement(style, "IconStyle")
        color = ET.SubElement(icon, "color")
        color.text = _hex_to_kml_abgr(hex_color)
        scale = ET.SubElement(icon, "scale")
        scale.text = "1.1"

    def add_folder(name: str, style_kind: str, items: list[dict[str, Any]]) -> int:
        folder = ET.SubElement(doc, "Folder")
        ET.SubElement(folder, "name").text = name
        count = 0
        for it in items:
            lat = it.get("gps_lat")
            lon = it.get("gps_lon")
            if not _gps_ok(lat, lon):
                continue
            cls = str(it.get("class_name") or style_kind)
            alt = float(it.get("gps_alt") or 0)
            pm = ET.SubElement(folder, "Placemark")
            ET.SubElement(pm, "name").text = cls
            desc_parts = [f"change={style_kind}", f"class={cls}"]
            if it.get("confidence") is not None:
                desc_parts.append(f"confidence={it.get('confidence')}")
            if it.get("distance_m") is not None:
                desc_parts.append(f"distance_m={it.get('distance_m')}")
            ET.SubElement(pm, "description").text = "\n".join(desc_parts)
            ET.SubElement(pm, "styleUrl").text = f"#chg_{style_kind}"
            point = ET.SubElement(pm, "Point")
            coords = ET.SubElement(point, "coordinates")
            coords.text = f"{float(lon)},{float(lat)},{alt}"
            count += 1
        return count

    new_items = list(result.get("new") or [])
    removed_items = list(result.get("removed") or [])
    moved_items: list[dict[str, Any]] = []
    for m in result.get("matches") or []:
        if m.get("status") != "moved":
            continue
        # Prefer after GPS if present on match; matches usually only have bboxes
        item = {
            "class_name": m.get("class_name"),
            "distance_m": m.get("distance_m"),
            "gps_lat": m.get("gps_lat") or m.get("after_gps_lat"),
            "gps_lon": m.get("gps_lon") or m.get("after_gps_lon"),
            "gps_alt": m.get("gps_alt") or m.get("after_gps_alt"),
        }
        # Enrich from paired new/removed lists is not available; skip if no GPS
        moved_items.append(item)

    n_new = add_folder("New", "new", new_items)
    n_rem = add_folder("Removed", "removed", removed_items)
    n_mov = add_folder("Moved", "moved", moved_items)

    # Update description with placemark counts
    desc_el = doc.find("description")
    if desc_el is not None:
        desc_el.text = (
            f"{desc_el.text}; placemarks new={n_new} removed={n_rem} moved={n_mov}"
        )

    return ET.tostring(kml, encoding="utf-8", xml_declaration=True).decode("utf-8")
