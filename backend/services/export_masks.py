"""Export segmentation masks as GeoTIFF or KML.

GPS gate: GeoTIFF requires GPS on source detection.
KML reuses detection GPS; skips mask if missing.

FIXED per grilling C1-C5, M1-M3, R1-R4, G-A-G-E, H1-H4, K1-K3:
- C1: detection_id path resolves time_sec from DB first
- C2: KML Polygon → outerBoundaryIs/LinearRing/coordinates (OGC spec)
- C3: rasterio-only, no toy manual GeoTIFF → 503 geo_libs_missing
- C4: module-level rasterio import (None on ImportError)
- C5: list_detections returns list[dict] (not sqlite3.Row) — verified
- M1: GPS gate detail uses disabled_reason key
- M2: approximate georef documented (center=GPS + normalized offset ~10m)
- M3: masks only available from in-memory results (not persisted)
- R1: filter by status["video_path"] FIRST, then time_sec tolerance
- R2: `from services.db import list_detections` at module level
- R3: endpoints accept optional `time_sec` query param
- R4: dims from task meta (not hardcoded 1024); first-mask-only documented
- G-A: frame_w/frame_h in batch_seg/sam3_prop status() returns
- G-C: kml endpoint passes time_sec (parity with geotiff)
- G-E: endpoint passes frame_w/frame_h from status meta to build_masks_geotiff
- H1: deleted duplicate broken tests (SyntaxError), kept fixed copies
- H2: None-safe dims chain (never .get on None)
- H3: frame_w/frame_h writer at first-frame load in both services
- K1: removed local import in _get_detection_gps (module-level used)
- K2: rasterio not in muravei_env → documented skip in KNOWN_ISSUES
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import cv2

from services import telemetry
from services.db import list_detections  # R2 fix: module-level import
from services.batch_segmentation import status as batch_seg_status
from services.sam3_propagate import status as sam3_prop_status

# Module-level rasterio import (C4 fix: module attribute, not local var)
_rasterio = None
try:
    import rasterio as _rasterio  # noqa: F401
    from rasterio.transform import from_origin

    _HAS_RASTERIO = True
except ImportError:
    _HAS_RASTERIO = False

# Expose rasterio module for test mocking (C4 fix)
rasterio = _rasterio


def resolve_masks_for_video(
    video_path: str,
    detection_id: str | None = None,
    time_sec: float | None = None,
) -> list[dict[str, Any]]:
    """Resolve mask data from batch seg / SAM3 propagate results for a video.

    C1 fix: detection_id path resolves time_sec from DB first.
    R1 fix: filter by status["video_path"] FIRST, then time_sec tolerance.
    """
    # C1 fix: if detection_id provided, resolve time_sec from DB
    if detection_id:
        time_sec = _resolve_detection_time_sec(detection_id)

    # Try batch seg first
    try:
        batch_status = batch_seg_status()
        if batch_status.get("results"):
            # R1 fix: filter by video_path from status first
            if batch_status.get("video_path") == video_path or not video_path:
                masks = _filter_masks(batch_status["results"], time_sec)
                if masks:
                    return masks
    except (KeyError, RuntimeError):
        pass

    # Try SAM3 propagate
    try:
        prop_status = sam3_prop_status()
        if prop_status.get("results"):
            # R1 fix: filter by video_path from status first
            if prop_status.get("video_path") == video_path or not video_path:
                masks = _filter_masks(prop_status["results"], time_sec)
                if masks:
                    return masks
    except (KeyError, RuntimeError):
        pass

    return []


def _resolve_detection_time_sec(detection_id: str) -> float | None:
    """C1 fix: resolve time_sec from detection by ID.
    R2 fix: uses module-level list_detections import.
    """
    rows = list_detections(include_deleted=False)
    for row in rows:
        if str(row.get("id")) == detection_id:
            return float(row.get("time_sec") or 0)
    return None


def _filter_masks(
    results: list[dict],
    time_sec: float | None,
) -> list[dict]:
    """Filter mask results by time_sec tolerance.

    C1 fix: results only have {time_sec, masks} — no source_video field.
    Without time_sec, return all results (batch export for any video).
    """
    filtered = []
    for r in results:
        if r.get("time_sec") is None:
            continue
        if time_sec is not None and abs(r["time_sec"] - time_sec) < 1.0:
            filtered.extend(r.get("masks", []))
        elif time_sec is None:
            # No time_sec filter — return all masks (batch export)
            filtered.extend(r.get("masks", []))
    return filtered


def _get_detection_gps(
    detection_id: str | None,
    video_path: str,
    time_sec: float | None,
) -> dict[str, float] | None:
    """Get GPS from detection or interpolate from telemetry.

    C5 fix: list_detections returns list[dict] (verified), so .get() works.
    K1 fix: removed local import — uses module-level import instead.
    """
    if detection_id:
        rows = list_detections(include_deleted=False)
        for row in rows:
            if str(row.get("id")) == detection_id:
                lat = row.get("gps_lat")
                lon = row.get("gps_lon")
                if lat and lon:
                    return {
                        "lat": float(lat),
                        "lon": float(lon),
                        "alt": float(row.get("gps_alt") or 0),
                    }
                # Try interpolation
                track = telemetry.load_track_points(str(video_path or ""))
                pt = telemetry.interpolate(track, float(time_sec or 0))
                if pt and pt.get("lat") and pt.get("lon"):
                    return {
                        "lat": float(pt["lat"]),
                        "lon": float(pt["lon"]),
                        "alt": float(pt.get("alt") or 0),
                    }
    elif time_sec is not None:
        track = telemetry.load_track_points(str(video_path or ""))
        pt = telemetry.interpolate(track, time_sec)
        if pt and pt.get("lat") and pt.get("lon"):
            return {
                "lat": float(pt["lat"]),
                "lon": float(pt["lon"]),
                "alt": float(pt.get("alt") or 0),
            }
    return None


def build_masks_kml(
    video_path: str,
    masks: list[dict[str, Any]],
    gps: dict[str, float] | None = None,
) -> str:
    """Build KML with mask polygons (not points).

    C2 fix: KML Polygon → outerBoundaryIs/LinearRing/coordinates (OGC spec).
    M2: approximate georef — center = GPS + normalized offset ~10m.
    """
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = f"MuraveiVision — Masks for {Path(video_path).name}"
    ET.SubElement(doc, "description").text = f"{len(masks)} masks exported"

    if not gps:
        return ET.tostring(kml, encoding="utf-8", xml_declaration=True).decode("utf-8")

    folder = ET.SubElement(doc, "Folder")
    ET.SubElement(folder, "name").text = Path(video_path).name

    for i, mask in enumerate(masks):
        polygon_norm = mask.get("polygon_norm", [])
        if not polygon_norm or len(polygon_norm) < 3:
            continue

        placemark = ET.SubElement(folder, "Placemark")
        ET.SubElement(placemark, "name").text = f"mask_{i}"
        cls = mask.get("class", "object")
        ET.SubElement(placemark, "description").text = f"class={cls}\nconf={mask.get('conf', 0)}"

        # C2 fix: OGC-compliant Polygon structure
        poly = ET.SubElement(placemark, "Polygon")
        outer = ET.SubElement(poly, "outerBoundaryIs")
        ring = ET.SubElement(outer, "LinearRing")
        coords = ET.SubElement(ring, "coordinates")

        # M2: approximate georef — center = GPS + normalized offset ~10m
        lat_c, lon_c = gps["lat"], gps["lon"]
        alt = gps.get("alt", 0)
        spread = 0.0001  # ~10m at mid-latitudes

        pts = []
        for nx, ny in polygon_norm:
            dlat = (ny - 0.5) * spread * 2
            dlon = (nx - 0.5) * spread * 2
            pts.append(f"{lon_c + dlon},{lat_c + dlat},{alt}")

        coords.text = "\n".join(pts) + f"\n{pts[0]}"

    return ET.tostring(kml, encoding="utf-8", xml_declaration=True).decode("utf-8")


def build_masks_geotiff(
    video_path: str,
    masks: list[dict[str, Any]],
    gps: dict[str, float],
    img_w: int = 1024,  # R4: default, override from task meta when available
    img_h: int = 1024,
) -> bytes:
    """Build valid GeoTIFF with mask polygons.

    C3 fix: rasterio-only, no toy manual fallback.
    M2/R4: dims from task meta (not hardcoded 1024); first-mask-only documented.
    """
    if not _HAS_RASTERIO:
        raise RuntimeError("geo_libs_missing: rasterio not installed")

    if not masks:
        return b""

    binary_mask = np.zeros((img_h, img_w), dtype=np.uint8)

    for mask in masks:
        polygon_norm = mask.get("polygon_norm", [])
        if not polygon_norm or len(polygon_norm) < 3:
            continue

        pts = np.array(
            [[int(p[0] * img_w), int(p[1] * img_h)] for p in polygon_norm],
            dtype=np.int32,
        )
        pts = pts.reshape((-1, 1, 2))
        cv2.fillPoly(binary_mask, [pts], 255)
        break  # M2: first mask only

    lat, lon = gps["lat"], gps["lon"]
    spread_m = 20.0
    deg_per_meter_lat = 1.0 / 111320.0
    deg_per_meter_lon = 1.0 / (111320.0 * np.cos(np.radians(lat)))

    transform = from_origin(
        lon - spread_m * deg_per_meter_lon,
        lat + spread_m * deg_per_meter_lat,
        2 * spread_m * deg_per_meter_lon,
        2 * spread_m * deg_per_meter_lat,
    )
    with _rasterio.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=img_h,
            width=img_w,
            count=1,
            dtype=np.uint8,
            transform=transform,
            crs="EPSG:4326",
        ) as dst:
            dst.write(binary_mask, 1)
        return memfile.getvalue()


def _check_geo_libs() -> tuple[bool, str]:
    """Check if geo libraries are available."""
    try:
        import numpy  # noqa: F401
    except ImportError:
        return False, "numpy unavailable"
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False, "opencv unavailable"
    if not _HAS_RASTERIO:
        return False, "rasterio unavailable"
    return True, ""
