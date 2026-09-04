"""P3.15.3: HTML report formatter for change detection results."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_bbox(bbox: dict[str, Any] | None) -> str:
    if not isinstance(bbox, dict):
        return "—"
    try:
        return (
            f"{float(bbox.get('x1', 0)):.3f},"
            f"{float(bbox.get('y1', 0)):.3f}–"
            f"{float(bbox.get('x2', 0)):.3f},"
            f"{float(bbox.get('y2', 0)):.3f}"
        )
    except (TypeError, ValueError):
        return "—"


def _fmt_gps(lat: Any, lon: Any) -> str:
    if lat is None or lon is None:
        return "—"
    try:
        return f"{float(lat):.6f}, {float(lon):.6f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_conf(conf: Any) -> str:
    if conf is None:
        return "—"
    try:
        return f"{float(conf) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _collect_gps_points(result: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in result.get("new") or []:
        if item.get("gps_lat") is not None and item.get("gps_lon") is not None:
            points.append(
                {
                    "kind": "new",
                    "lat": float(item["gps_lat"]),
                    "lon": float(item["gps_lon"]),
                    "label": item.get("class_name") or "new",
                }
            )
    for item in result.get("removed") or []:
        if item.get("gps_lat") is not None and item.get("gps_lon") is not None:
            points.append(
                {
                    "kind": "removed",
                    "lat": float(item["gps_lat"]),
                    "lon": float(item["gps_lon"]),
                    "label": item.get("class_name") or "removed",
                }
            )
    for m in result.get("matches") or []:
        if m.get("status") != "moved":
            continue
        # Prefer after coords if present on match payload; else skip map pin
        lat = m.get("gps_lat") or m.get("after_gps_lat")
        lon = m.get("gps_lon") or m.get("after_gps_lon")
        if lat is None or lon is None:
            continue
        try:
            points.append(
                {
                    "kind": "moved",
                    "lat": float(lat),
                    "lon": float(lon),
                    "label": f"{m.get('class_name') or 'moved'} ({m.get('distance_m')} m)",
                }
            )
        except (TypeError, ValueError):
            continue
    return points


def build_change_html(result: dict[str, Any], meta: dict[str, Any]) -> str:
    """Build a self-contained dark-theme HTML report for a change-detection result."""
    summary = result.get("summary") or {}
    generated = meta.get("generated_at") or datetime.now(timezone.utc).isoformat()
    video_before = _esc(meta.get("video_before") or "—")
    video_after = _esc(meta.get("video_after") or "—")
    time_before = meta.get("time_before")
    time_after = meta.get("time_after")
    method = _esc(result.get("method") or "none")
    message = result.get("message")

    new_rows = result.get("new") or []
    removed_rows = result.get("removed") or []
    moved_rows = [m for m in (result.get("matches") or []) if m.get("status") == "moved"]
    gps_points = _collect_gps_points(result)

    def rows_new_removed(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<tr><td colspan='4'>нет</td></tr>"
        parts: list[str] = []
        for it in items:
            parts.append(
                "<tr>"
                f"<td>{_esc(it.get('class_name'))}</td>"
                f"<td>{_fmt_conf(it.get('confidence'))}</td>"
                f"<td>{_esc(_fmt_bbox(it.get('bbox')))}</td>"
                f"<td>{_esc(_fmt_gps(it.get('gps_lat'), it.get('gps_lon')))}</td>"
                "</tr>"
            )
        return "".join(parts)

    def rows_moved(items: list[dict[str, Any]]) -> str:
        if not items:
            return "<tr><td colspan='4'>нет</td></tr>"
        parts: list[str] = []
        for m in items:
            parts.append(
                "<tr>"
                f"<td>{_esc(m.get('class_name'))}</td>"
                f"<td>{_esc(m.get('distance_m'))} m</td>"
                f"<td>{_esc(_fmt_bbox(m.get('before_bbox')))}</td>"
                f"<td>{_esc(_fmt_bbox(m.get('after_bbox')))}</td>"
                "</tr>"
            )
        return "".join(parts)

    map_block = ""
    if gps_points:
        import json

        from services import map_tiles as map_tiles_svc

        markers_json = json.dumps(gps_points, ensure_ascii=False)
        offline = map_tiles_svc.tiles_available()
        # Absolute URL so a downloaded HTML file can still load tiles while backend runs.
        tile_url = "http://127.0.0.1:8000/api/map/tiles/{z}/{x}/{y}.png"
        offline_js = "true" if offline else "false"
        if offline:
            tile_js = f"""
      L.tileLayer({json.dumps(tile_url)}, {{
        maxZoom: 19,
        attribution: 'Offline tiles'
      }}).addTo(map);
      var statusEl = document.getElementById('map-status');
      if (statusEl) statusEl.textContent = 'Офлайн карта';
"""
        else:
            tile_js = """
      var statusEl = document.getElementById('map-status');
      if (statusEl) {
        statusEl.textContent = 'Тайлы не установлены — см. docs/ENGINEER_GUIDE.md (офлайн карты)';
      }
"""
        map_block = f"""
<section style="position:relative;">
  <h2>Карта (GPS)</h2>
  <div id="map-status" style="margin:0 0 8px;font-size:0.8rem;color:var(--muted);"></div>
  <div id="map" style="height:360px;border:1px solid #333;border-radius:4px;"></div>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    (function() {{
      var points = {markers_json};
      var tilesAvailable = {offline_js};
      if (!points.length || typeof L === 'undefined') return;
      var map = L.map('map');
      {tile_js}
      var colors = {{new:'#22c55e', removed:'#ef4444', moved:'#eab308'}};
      var bounds = [];
      points.forEach(function(p) {{
        var m = L.circleMarker([p.lat, p.lon], {{
          radius: 7,
          color: colors[p.kind] || '#94a3b8',
          fillColor: colors[p.kind] || '#94a3b8',
          fillOpacity: 0.85
        }}).addTo(map);
        m.bindPopup((p.kind || '') + ': ' + (p.label || ''));
        bounds.push([p.lat, p.lon]);
      }});
      map.fitBounds(bounds, {{padding: [24, 24]}});
      void tilesAvailable;
    }})();
  </script>
</section>
"""

    msg_html = f"<p class='warn'>{_esc(message)}</p>" if message else ""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<title>MuraveiVision — отчёт изменений</title>
<style>
  :root {{ --bg:#0f1115; --panel:#1a1d24; --border:#2a2f3a; --text:#e8eaed; --muted:#9aa3b2; --accent:#e87d0d; }}
  body {{ margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--text); }}
  main {{ max-width:960px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ font-size:1.35rem; margin:0 0 8px; color:var(--accent); }}
  h2 {{ font-size:1rem; margin:24px 0 8px; border-bottom:1px solid var(--border); padding-bottom:4px; }}
  .meta {{ color:var(--muted); font-size:0.85rem; line-height:1.5; }}
  .warn {{ color:#fbbf24; font-size:0.85rem; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); font-size:0.8rem; }}
  th, td {{ border:1px solid var(--border); padding:6px 8px; text-align:left; }}
  th {{ background:#12151b; color:var(--muted); font-weight:600; }}
  .summary td:first-child {{ width:40%; color:var(--muted); }}
</style>
</head>
<body>
<main>
  <h1>Отчёт изменений (Compare Sync)</h1>
  <div class="meta">
    <div>Сформирован: {_esc(generated)}</div>
    <div>Было: {video_before} @ {_esc(time_before)} с</div>
    <div>Стало: {video_after} @ {_esc(time_after)} с</div>
    <div>Метод: {method}</div>
  </div>
  {msg_html}

  <h2>Сводка</h2>
  <table class="summary">
    <tr><td>Всего было</td><td>{_esc(summary.get('total_before', 0))}</td></tr>
    <tr><td>Всего стало</td><td>{_esc(summary.get('total_after', 0))}</td></tr>
    <tr><td>Сопоставлено</td><td>{_esc(summary.get('matched', 0))}</td></tr>
    <tr><td>Стабильные</td><td>{_esc(summary.get('stable', 0))}</td></tr>
    <tr><td>Перемещены</td><td>{_esc(summary.get('moved', 0))}</td></tr>
    <tr><td>Новые</td><td>{_esc(summary.get('new', 0))}</td></tr>
    <tr><td>Исчезли</td><td>{_esc(summary.get('removed', 0))}</td></tr>
  </table>

  <h2>Новые</h2>
  <table>
    <thead><tr><th>Класс</th><th>Conf</th><th>BBox</th><th>GPS</th></tr></thead>
    <tbody>{rows_new_removed(new_rows)}</tbody>
  </table>

  <h2>Исчезли</h2>
  <table>
    <thead><tr><th>Класс</th><th>Conf</th><th>BBox</th><th>GPS</th></tr></thead>
    <tbody>{rows_new_removed(removed_rows)}</tbody>
  </table>

  <h2>Перемещены</h2>
  <table>
    <thead><tr><th>Класс</th><th>Дистанция</th><th>BBox было</th><th>BBox стало</th></tr></thead>
    <tbody>{rows_moved(moved_rows)}</tbody>
  </table>

  {map_block}
</main>
</body>
</html>
"""


def build_batch_change_html(
    aggregate: dict[str, Any] | None,
    results: list[dict[str, Any]],
    meta: dict[str, Any],
) -> str:
    """HTML report for P3.15.5 batch CD (aggregate + per-pair table)."""
    generated = meta.get("generated_at") or datetime.now(timezone.utc).isoformat()
    video_before = _esc(meta.get("video_before") or "—")
    video_after = _esc(meta.get("video_after") or "—")
    agg = aggregate or {}
    sync_method = _esc(agg.get("sync_method") or meta.get("sync_method") or "—")

    pair_rows: list[str] = []
    if not results:
        pair_rows.append("<tr><td colspan='7'>нет пар</td></tr>")
    else:
        for row in results:
            summary = row.get("summary") or {}
            pair_rows.append(
                "<tr>"
                f"<td>{_esc(row.get('time_before'))}</td>"
                f"<td>{_esc(row.get('time_after'))}</td>"
                f"<td>{_esc(row.get('method'))}</td>"
                f"<td>{_esc(summary.get('new', 0))}</td>"
                f"<td>{_esc(summary.get('removed', 0))}</td>"
                f"<td>{_esc(summary.get('moved', 0))}</td>"
                f"<td>{_esc(summary.get('stable', 0))}</td>"
                "</tr>"
            )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<title>MuraveiVision — пакетный отчёт изменений</title>
<style>
  :root {{ --bg:#0f1115; --panel:#1a1d24; --border:#2a2f3a; --text:#e8eaed; --muted:#9aa3b2; --accent:#e87d0d; }}
  body {{ margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--text); }}
  main {{ max-width:960px; margin:0 auto; padding:24px 16px 48px; }}
  h1 {{ font-size:1.35rem; margin:0 0 8px; color:var(--accent); }}
  h2 {{ font-size:1rem; margin:24px 0 8px; border-bottom:1px solid var(--border); padding-bottom:4px; }}
  .meta {{ color:var(--muted); font-size:0.85rem; line-height:1.5; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel); font-size:0.8rem; }}
  th, td {{ border:1px solid var(--border); padding:6px 8px; text-align:left; }}
  th {{ background:#12151b; color:var(--muted); font-weight:600; }}
  .summary td:first-child {{ width:50%; color:var(--muted); }}
</style>
</head>
<body>
<main>
  <h1>Пакетный отчёт изменений (Batch CD)</h1>
  <div class="meta">
    <div>Сформирован: {_esc(generated)}</div>
    <div>Было: {video_before}</div>
    <div>Стало: {video_after}</div>
    <div>Синхронизация: {sync_method}</div>
  </div>

  <h2>Сводка (уникальные ID)</h2>
  <table class="summary">
    <tr><td>Пар обработано</td><td>{_esc(agg.get('pair_count', len(results)))}</td></tr>
    <tr><td>Уник. новые</td><td>{_esc(agg.get('unique_new', 0))}</td></tr>
    <tr><td>Уник. исчезли</td><td>{_esc(agg.get('unique_removed', 0))}</td></tr>
    <tr><td>Уник. перемещены</td><td>{_esc(agg.get('unique_moved', 0))}</td></tr>
    <tr><td>Сумма new (по парам)</td><td>{_esc(agg.get('sum_new', 0))}</td></tr>
    <tr><td>Сумма removed (по парам)</td><td>{_esc(agg.get('sum_removed', 0))}</td></tr>
    <tr><td>Сумма moved (по парам)</td><td>{_esc(agg.get('sum_moved', 0))}</td></tr>
  </table>

  <h2>Пары</h2>
  <table>
    <thead>
      <tr>
        <th>t было, с</th><th>t стало, с</th><th>Метод</th>
        <th>New</th><th>Removed</th><th>Moved</th><th>Stable</th>
      </tr>
    </thead>
    <tbody>{"".join(pair_rows)}</tbody>
  </table>
</main>
</body>
</html>
"""