"""Air-gapped HTML report: tactical dashboard matching the operator template."""
from __future__ import annotations

import base64
import html
import platform as py_platform
from collections import Counter, defaultdict
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from config import BASE_DIR
from services.db import CROPS_DIR, list_detections
from services.hardware import hardware_spec

REPORTS_DIR = BASE_DIR / "reports"
APP_VERSION = "3.0"

_PLACEHOLDER = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)

_STATUS_LABEL = {
    "confirmed": "Confirmed",
    "false-positive": "False Positive",
    "pending": "Pending",
}


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _fmt_time(sec: float) -> str:
    total = max(0, int(round(float(sec))))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _crop_data_uri(row: dict[str, Any]) -> str:
    candidates: list[Path] = []
    if row.get("crop_path"):
        candidates.append(Path(str(row["crop_path"])))
    det_id = row.get("id")
    if det_id:
        candidates.append(CROPS_DIR / f"{det_id}.jpg")
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return _PLACEHOLDER
    try:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        img.thumbnail((100, 100))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        try:
            return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        except Exception:
            return _PLACEHOLDER


def _norm_class(name: Any) -> str:
    return str(name or "").strip().lower()


def _status_of(row: dict[str, Any]) -> str:
    if row.get("is_deleted"):
        return "false-positive"
    if row.get("is_edited") or str(row.get("origin") or "") == "manual":
        return "confirmed"
    return "pending"


def _active_model_name() -> str:
    try:
        from services import yolo_engine as ye

        engine = ye._engine
        if engine is not None and getattr(engine, "model_name", ""):
            return str(engine.model_name)
        for cand in [
            ye.WEIGHTS_DIR / "yoloe-26s-seg.pt",
            ye.WEIGHTS_DIR / "yoloe-26n-seg.pt",
            ye.WEIGHTS_DIR / "yoloe-26s-seg-pf.pt",
            ye.WEIGHTS_DIR / "yolo26n.pt",
            ye.WEIGHTS_DIR / "yolo26s.pt",
            BASE_DIR / "assets" / "models" / "best.pt",
        ]:
            if cand.is_file() and cand.stat().st_size > 1024:
                return cand.name
    except Exception:
        pass
    return "yolo26n.pt"


def _video_label(rows: list[dict[str, Any]]) -> str:
    names = [Path(str(r.get("source_video") or "")).name or str(r.get("source_video") or "—") for r in rows]
    if not names:
        return "—"
    counts = Counter(names)
    top, _ = counts.most_common(1)[0]
    extra = len(counts) - 1
    return f"{top} (+{extra})" if extra > 0 else top


def _operator_id(rows: list[dict[str, Any]]) -> str:
    editors = [str(r["edited_by"]) for r in rows if r.get("edited_by")]
    if editors:
        return Counter(editors).most_common(1)[0][0]
    return "operator"


def _platform_label(hw: dict[str, Any] | None = None) -> str:
    hw = hw or {}
    sysname = py_platform.system()
    rel = py_platform.release()
    plat = f"{sysname} {rel}".strip() or str(hw.get("platform") or "—")
    gpu = str(hw.get("gpu") or "").split(",")[0].strip()
    if gpu and "not found" not in gpu.lower():
        gpu = gpu.replace("NVIDIA GeForce ", "").replace("NVIDIA ", "")
        return f"{plat} · {gpu}"
    return plat


def _build_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        ai_cls = str(row.get("ai_class_name") or row.get("class_name") or "")
        op_cls = str(row.get("class_name") or "")
        corrected = bool(ai_cls) and bool(op_cls) and _norm_class(ai_cls) != _norm_class(op_cls)
        t = float(row.get("time_sec") or 0)
        items.append(
            {
                "id": str(row.get("id") or ""),
                "ts": _fmt_time(t),
                "t": t,
                "img": _crop_data_uri(row),
                "ai_class": ai_cls,
                "op_class": op_cls,
                "conf": int(round(float(row.get("confidence") or 0) * 100)),
                "notes": str(row.get("user_notes") or ""),
                "status": _status_of(row),
                "corrected": corrected,
                "src": Path(str(row.get("source_video") or "")).name,
                "gps_lat": row.get("gps_lat"),
                "gps_lon": row.get("gps_lon"),
                "gps_alt": row.get("gps_alt"),
                "source_video": str(row.get("source_video") or ""),
            }
        )
    return items


def _svg_flight_map(
    track: list[dict[str, Any]],
    items: list[dict[str, Any]],
    *,
    width: int = 720,
    height: int = 360,
) -> str:
    """Orthographic SVG: lon→x, lat→y. No external tiles."""
    pts = [
        (float(p["lon"]), float(p["lat"]))
        for p in track
        if p.get("lat") is not None and p.get("lon") is not None
    ]
    dets = [
        (float(it["gps_lon"]), float(it["gps_lat"]), str(it.get("op_class") or ""), str(it.get("ts") or ""))
        for it in items
        if it.get("gps_lat") is not None and it.get("gps_lon") is not None
    ]
    if not pts and not dets:
        return ""
    all_xy = pts + [(d[0], d[1]) for d in dets]
    lons = [p[0] for p in all_xy]
    lats = [p[1] for p in all_xy]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    pad = 0.08
    span_lon = max(max_lon - min_lon, 1e-6)
    span_lat = max(max_lat - min_lat, 1e-6)
    min_lon -= span_lon * pad
    max_lon += span_lon * pad
    min_lat -= span_lat * pad
    max_lat += span_lat * pad
    span_lon = max_lon - min_lon
    span_lat = max_lat - min_lat
    margin = 24

    def xy(lon: float, lat: float) -> tuple[float, float]:
        x = margin + (lon - min_lon) / span_lon * (width - 2 * margin)
        y = height - margin - (lat - min_lat) / span_lat * (height - 2 * margin)
        return x, y

    poly = " ".join(f"{xy(lon, lat)[0]:.1f},{xy(lon, lat)[1]:.1f}" for lon, lat in pts)
    circles = []
    for lon, lat, cls, ts in dets:
        cx, cy = xy(lon, lat)
        title = _esc(f"{cls} @ {ts} ({lat:.5f},{lon:.5f})")
        circles.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="#00ff88" stroke="#0a0a0a" '
            f'stroke-width="1"><title>{title}</title></circle>'
        )
    poly_el = (
        f'<polyline fill="none" stroke="#38bdf8" stroke-width="2" points="{poly}"/>'
        if poly
        else ""
    )
    return f"""
<div class="flight-map">
  <h3>Траектория полёта (SVG)</h3>
  <svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Flight track">
    <rect x="0" y="0" width="{width}" height="{height}" fill="#111" stroke="#333"/>
    {poly_el}
    {''.join(circles)}
  </svg>
  <div class="map-legend">линия — телеметрия · точки — детекции с GPS</div>
</div>
"""


def _load_track_for_report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    try:
        from services.db import get_flight_track
        from services.telemetry import load_track_points
    except Exception:
        return []
    counts: Counter[str] = Counter(str(r.get("source_video") or "") for r in rows)
    top = counts.most_common(1)[0][0] if counts else ""
    if not top:
        return []
    row = get_flight_track(top)
    if row and row.get("points"):
        return list(row["points"])
    try:
        return load_track_points(top)
    except Exception:
        return []

_CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #0a0a0a;
    color: #e0e0e0;
    padding: 24px;
    line-height: 1.4;
  }
  .header {
    border-bottom: 2px solid #00ff88;
    padding-bottom: 16px;
    margin-bottom: 24px;
  }
  .header h1 {
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 1px;
    color: #00ff88;
    text-transform: uppercase;
  }
  .header .subtitle {
    font-size: 12px;
    color: #888;
    margin-top: 4px;
  }
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .meta-item {
    background: #141414;
    border: 1px solid #2a2a2a;
    padding: 8px 12px;
    font-size: 12px;
  }
  .meta-item .label { color: #888; font-size: 10px; text-transform: uppercase; }
  .meta-item .value { color: #e0e0e0; font-weight: 500; margin-top: 2px; word-break: break-all; }
  .dashboard {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: #141414;
    border: 1px solid #2a2a2a;
    padding: 16px;
  }
  .stat-card .stat-label {
    font-size: 10px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .stat-card .stat-value {
    font-size: 32px;
    font-weight: 700;
    margin-top: 4px;
  }
  .stat-card.total .stat-value { color: #0d96dc; }
  .stat-card.confirmed .stat-value { color: #00ff88; }
  .stat-card.rejected .stat-value { color: #ff4444; }
  .stat-card.classes .stat-value { color: #ffaa00; }
  .class-bars {
    background: #141414;
    border: 1px solid #2a2a2a;
    padding: 16px;
    margin-bottom: 24px;
  }
  .class-bars h3 {
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    margin-bottom: 12px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: 140px 1fr 100px;
    gap: 12px;
    align-items: center;
    margin-bottom: 6px;
    font-size: 12px;
  }
  .bar-name { color: #e0e0e0; font-family: ui-monospace, "Consolas", monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-track {
    background: #0a0a0a;
    height: 8px;
    border-radius: 2px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #00ff88, #0d96dc);
  }
  .bar-count { color: #888; text-align: right; white-space: nowrap; min-width: 90px; }
  .controls {
    background: #141414;
    border: 1px solid #2a2a2a;
    padding: 12px 16px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 24px;
    position: sticky;
    top: 0;
    z-index: 20;
  }
  .control-group {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .control-label {
    font-size: 10px;
    color: #888;
    text-transform: uppercase;
    margin-right: 4px;
  }
  .filter-btn {
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    color: #e0e0e0;
    padding: 4px 10px;
    font-size: 11px;
    cursor: pointer;
    border-radius: 2px;
  }
  .filter-btn:hover { border-color: #00ff88; }
  .filter-btn.active { background: #00ff88; color: #0a0a0a; border-color: #00ff88; }
  .filter-btn.confirmed.active { background: #00ff88; }
  .filter-btn.false-positive.active { background: #ff4444; color: #fff; }
  .filter-btn.pending.active { background: #ffaa00; color: #0a0a0a; }
  .search-input {
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    color: #e0e0e0;
    padding: 4px 10px;
    font-size: 11px;
    width: 200px;
  }
  .search-input:focus { outline: none; border-color: #0d96dc; }
  .sort-select {
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    color: #e0e0e0;
    padding: 4px 10px;
    font-size: 11px;
  }
  .group { margin-bottom: 24px; }
  .group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: #141414;
    border-left: 3px solid #0d96dc;
    margin-bottom: 12px;
    cursor: pointer;
  }
  .group-header h2 {
    font-size: 13px;
    font-weight: 600;
    font-family: ui-monospace, "Consolas", monospace;
  }
  .group-header .count { font-size: 11px; color: #888; }
  .group-header .toggle { font-size: 11px; color: #0d96dc; }
  .detection-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }
  .detection-card {
    background: #141414;
    border: 1px solid #2a2a2a;
    padding: 12px;
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 12px;
    transition: border-color 0.2s;
    page-break-inside: avoid;
    break-inside: avoid;
  }
  .detection-card:hover { border-color: #0d96dc; }
  .detection-card.confirmed { border-left: 3px solid #00ff88; }
  .detection-card.false-positive { border-left: 3px solid #ff4444; }
  .detection-card.pending { border-left: 3px solid #ffaa00; }
  .detection-card.edited { border-left: 3px solid #0d96dc; }
  .crop-thumb {
    width: 100px;
    height: 100px;
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    color: #555;
    overflow: hidden;
  }
  .crop-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .card-body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .timecode {
    font-family: ui-monospace, "Consolas", monospace;
    font-size: 14px;
    font-weight: 600;
    color: #0d96dc;
  }
  .class-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
  }
  .class-row .label { color: #888; }
  .class-row .value { color: #e0e0e0; font-weight: 500; text-align: right; }
  .class-row .value.edited {
    color: #0d96dc;
    text-decoration: underline;
  }
  .confidence-badge {
    display: inline-block;
    background: #0a0a0a;
    padding: 2px 6px;
    border-radius: 2px;
    font-size: 10px;
    font-family: ui-monospace, "Consolas", monospace;
  }
  .status-badge {
    display: inline-block;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-radius: 2px;
    margin-top: 4px;
    width: fit-content;
  }
  .status-badge.confirmed { background: #00ff88; color: #0a0a0a; }
  .status-badge.false-positive { background: #ff4444; color: #fff; }
  .status-badge.pending { background: #ffaa00; color: #0a0a0a; }
  .note {
    font-size: 11px;
    color: #888;
    font-style: italic;
    margin-top: 4px;
    padding-top: 4px;
    border-top: 1px solid #2a2a2a;
  }
  .footer {
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid #2a2a2a;
    font-size: 10px;
    color: #555;
    text-align: center;
  }
  .flight-map {
    margin: 24px 0;
    padding: 16px;
    border: 1px solid #333;
    background: #0d0d0d;
  }
  .flight-map h3 {
    font-size: 14px;
    margin-bottom: 12px;
    color: #00ff88;
  }
  .flight-map svg {
    display: block;
    max-width: 100%;
    height: auto;
  }
  .map-legend {
    margin-top: 8px;
    font-size: 11px;
    color: #888;
  }
  .gps-line {
    font-family: ui-monospace, Consolas, monospace;
    font-size: 10px;
    color: #38bdf8;
    margin-top: 4px;
  }
  .empty { color: #888; padding: 16px; font-size: 13px; }
  @media print {
    body { background: #fff; color: #000; padding: 12px; }
    .controls, .group-header .toggle { display: none !important; }
    .detection-card, .stat-card, .class-bars, .meta-item {
      background: #fff;
      border-color: #000;
      color: #000;
    }
    .detection-card { page-break-inside: avoid; }
    .stat-card .stat-value, .timecode { color: #000; }
    .header h1 { color: #000; }
    .header { border-color: #000; }
  }
  @media (max-width: 1200px) {
    .detection-grid { grid-template-columns: repeat(2, 1fr); }
    .dashboard { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 768px) {
    .detection-grid { grid-template-columns: 1fr; }
    .dashboard { grid-template-columns: 1fr; }
    .detection-card { grid-template-columns: 1fr; }
    .crop-thumb { width: 100%; height: 150px; }
  }
"""

_JS = """
  document.querySelectorAll('.status-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.status-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyFilters();
    });
  });
  document.getElementById('class-filter').addEventListener('change', applyFilters);
  document.getElementById('search-input').addEventListener('input', applyFilters);
  document.getElementById('sort-select').addEventListener('change', applySort);

  function applyFilters() {
    const status = document.querySelector('.status-btn.active').dataset.status;
    const cls = document.getElementById('class-filter').value;
    const search = document.getElementById('search-input').value.toLowerCase();
    document.querySelectorAll('.detection-card').forEach(card => {
      const matchStatus = status === 'all' || card.dataset.status === status;
      const matchClass = cls === 'all' || card.dataset.class === cls;
      const note = (card.dataset.notes || card.querySelector('.note')?.textContent || '').toLowerCase();
      const hay = (note + ' ' + (card.dataset.class || '') + ' ' + (card.dataset.time || '')).toLowerCase();
      const matchSearch = !search || hay.includes(search);
      card.style.display = (matchStatus && matchClass && matchSearch) ? '' : 'none';
    });
    document.querySelectorAll('.group').forEach(group => {
      const vis = Array.from(group.querySelectorAll('.detection-card')).some(c => c.style.display !== 'none');
      group.style.display = vis ? '' : 'none';
    });
  }

  function applySort() {
    const sortBy = document.getElementById('sort-select').value;
    document.querySelectorAll('.detection-grid').forEach(grid => {
      const cards = Array.from(grid.children);
      cards.sort((a, b) => {
        if (sortBy === 'time') return a.dataset.time.localeCompare(b.dataset.time);
        if (sortBy === 'confidence') return parseInt(b.dataset.confidence, 10) - parseInt(a.dataset.confidence, 10);
        if (sortBy === 'class') return a.dataset.class.localeCompare(b.dataset.class);
        return 0;
      });
      cards.forEach(c => grid.appendChild(c));
    });
  }

  document.querySelectorAll('.group-header').forEach(header => {
    header.addEventListener('click', () => {
      const grid = header.nextElementSibling;
      const toggle = header.querySelector('.toggle');
      if (grid.style.display === 'none') {
        grid.style.display = '';
        toggle.textContent = '▼ Свернуть';
      } else {
        grid.style.display = 'none';
        toggle.textContent = '▶ Развернуть';
      }
    });
  });
"""


def _card_html(it: dict[str, Any]) -> str:
    status = it["status"]
    extra = " edited" if it["corrected"] else ""
    op_cls = it["op_class"]
    if it["corrected"]:
        op_html = f'<span class="value edited">{_esc(op_cls)} &#9998;</span>'
    else:
        op_html = f'<span class="value">{_esc(op_cls)}</span>'
    notes = it["notes"]
    note_html = f'<div class="note">"{_esc(notes)}"</div>' if notes else ""
    gps_html = ""
    if it.get("gps_lat") is not None and it.get("gps_lon") is not None:
        alt = ""
        if it.get("gps_alt") is not None:
            alt = f" · alt {float(it['gps_alt']):.1f}m"
        gps_html = (
            f'<div class="gps-line">{float(it["gps_lat"]):.6f}, '
            f'{float(it["gps_lon"]):.6f}{alt}</div>'
        )
    return f"""
    <div class="detection-card {status}{extra}" data-status="{_esc(status)}" data-class="{_esc(op_cls)}" data-notes="{_esc(notes)}" data-time="{_esc(it["ts"])}" data-confidence="{int(it["conf"])}">
      <div class="crop-thumb"><img src="{it["img"]}" alt="crop"></div>
      <div class="card-body">
        <div class="timecode">{_esc(it["ts"])}</div>
        <div class="class-row"><span class="label">Класс ИИ:</span><span class="value">{_esc(it["ai_class"])} <span class="confidence-badge">{int(it["conf"])}%</span></span></div>
        <div class="class-row"><span class="label">Класс оператора:</span>{op_html}</div>
        <span class="status-badge {status}">{_STATUS_LABEL[status]}</span>
        {gps_html}
        {note_html}
      </div>
    </div>
"""


def _groups_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty">Нет сохранённых детекций.</p>'
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        buckets[int(it["t"]) // 60].append(it)
    parts: list[str] = []
    for minute in sorted(buckets):
        chunk = buckets[minute]
        start = _fmt_time(minute * 60)
        end = _fmt_time(minute * 60 + 59)
        key = start[:5]
        cards = "".join(_card_html(it) for it in chunk)
        parts.append(
            f'<div class="group" data-group="{_esc(key)}">'
            f'<div class="group-header">'
            f"<h2>{start} – {end}</h2>"
            f'<div><span class="count">{len(chunk)} детекций</span> <span class="toggle">▼ Свернуть</span></div>'
            f"</div>"
            f'<div class="detection-grid">{cards}</div>'
            f"</div>"
        )
    return "".join(parts)


def render_report_html(
    *,
    created: str,
    operator_id: str,
    source_video: str,
    model_name: str,
    duration: str,
    platform: str,
    items: list[dict[str, Any]],
    map_svg: str = "",
) -> str:
    total = len(items)
    confirmed = sum(1 for it in items if it["status"] == "confirmed")
    rejected = sum(1 for it in items if it["status"] == "false-positive")
    unique_names = [it["op_class"] for it in items if it["op_class"]]
    unique = len(set(unique_names))
    counts = Counter(unique_names)
    denom = sum(counts.values()) or 1
    bars = "".join(
        f'<div class="bar-row"><div class="bar-name">{_esc(name)}</div>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{round(100.0 * n / denom, 1)}%"></div></div>'
        f'<div class="bar-count">{n} ({round(100.0 * n / denom, 1)}%)</div></div>'
        for name, n in counts.most_common()
    ) or '<p class="empty">Нет классов.</p>'
    class_opts = "".join(
        f'<option value="{_esc(name)}">{_esc(name)}</option>' for name, _n in counts.most_common()
    )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MuraveiVision PRO — Отчёт анализа</title>
<style>
{_CSS}
</style>
</head>
<body>

<div class="header">
  <h1>MuraveiVision PRO // Автономный отчёт анализа</h1>
  <div class="subtitle">Сформировано: {_esc(created)}</div>
  <div class="meta-grid">
    <div class="meta-item"><div class="label">Оператор</div><div class="value">{_esc(operator_id)}</div></div>
    <div class="meta-item"><div class="label">Исходный файл</div><div class="value">{_esc(source_video)}</div></div>
    <div class="meta-item"><div class="label">Модель</div><div class="value">{_esc(model_name)}</div></div>
    <div class="meta-item"><div class="label">Длительность</div><div class="value">{_esc(duration)}</div></div>
    <div class="meta-item"><div class="label">Платформа</div><div class="value">{_esc(platform)}</div></div>
  </div>
</div>

<div class="dashboard">
  <div class="stat-card total">
    <div class="stat-label">Всего детекций</div>
    <div class="stat-value">{total}</div>
  </div>
  <div class="stat-card confirmed">
    <div class="stat-label">Подтверждено</div>
    <div class="stat-value">{confirmed}</div>
  </div>
  <div class="stat-card rejected">
    <div class="stat-label">Отклонено</div>
    <div class="stat-value">{rejected}</div>
  </div>
  <div class="stat-card classes">
    <div class="stat-label">Уникальных классов</div>
    <div class="stat-value">{unique}</div>
  </div>
</div>

<div class="class-bars">
  <h3>Разбивка по классам</h3>
  {bars}
</div>

{map_svg}

<div class="controls">
  <div class="control-group">
    <span class="control-label">Статус:</span>
    <button class="filter-btn status-btn active" data-status="all">Все</button>
    <button class="filter-btn status-btn confirmed" data-status="confirmed">Confirmed</button>
    <button class="filter-btn status-btn false-positive" data-status="false-positive">False Positive</button>
    <button class="filter-btn status-btn pending" data-status="pending">Pending</button>
  </div>
  <div class="control-group">
    <span class="control-label">Класс:</span>
    <select class="sort-select" id="class-filter">
      <option value="all">Все классы</option>
      {class_opts}
    </select>
  </div>
  <div class="control-group">
    <span class="control-label">Поиск:</span>
    <input type="text" class="search-input" id="search-input" placeholder="По заметкам...">
  </div>
  <div class="control-group">
    <span class="control-label">Сортировка:</span>
    <select class="sort-select" id="sort-select">
      <option value="time">По времени</option>
      <option value="confidence">По уверенности</option>
      <option value="class">По классу</option>
    </select>
  </div>
</div>

{_groups_html(items)}

<div class="footer">
  Сгенерировано автоматически. Документ содержит служебную информацию. MuraveiVision v{APP_VERSION}
</div>

<script>
{_JS}
</script>

</body>
</html>
"""


def sample_template_items() -> list[dict[str, Any]]:
    """Static rows for report_template.html only — not used in live exports."""
    def row(
        ts: str,
        t: float,
        ai: str,
        op: str,
        conf: int,
        status: str,
        notes: str = "",
        corrected: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": ts,
            "ts": ts,
            "t": t,
            "img": _PLACEHOLDER,
            "ai_class": ai,
            "op_class": op,
            "conf": conf,
            "notes": notes,
            "status": status,
            "corrected": corrected,
            "src": "video_2026-08-24_22-29-43.mp4",
        }

    return [
        row("00:00:02", 2, "soldier", "soldier", 100, "confirmed"),
        row("00:00:02", 2.1, "tank", "artillery_mlrs", 100, "false-positive", "Ложная тревога, тень от дерева", True),
        row("00:00:04", 4, "quadcopter_drone", "quadcopter_drone", 100, "confirmed"),
        row("00:00:04", 4.1, "anti_personnel_mine", "anti_personnel_mine", 62, "false-positive"),
        row("00:00:04", 4.2, "tripwire_booby_trap", "tripwire_booby_trap", 44, "pending", "Требует проверки оператором"),
        row("00:00:07", 7, "soldier", "soldier", 100, "confirmed"),
        row("00:00:10", 10, "tank", "armored_vehicle", 87, "confirmed", "Бронемашина, не ОБТ.", True),
        row("00:00:14", 14, "soldier", "soldier", 55, "false-positive", "Силуэт куста"),
        row("00:00:18", 18, "uav", "uav", 71, "pending"),
        row("00:00:22", 22, "tank", "tank", 93, "confirmed", "Подтверждаю, танк на грунтовке."),
    ]


def write_report_template() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_doc = render_report_html(
        created="2026-08-25 01:50:11 UTC",
        operator_id="operator",
        source_video="video_2026-08-24_22-29-43.mp4",
        model_name="yoloe-26s-seg.pt",
        duration="00:00:22",
        platform="Windows 11 · RTX 5060 8GB",
        items=sample_template_items(),
    )
    dest = REPORTS_DIR / "report_template.html"
    dest.write_text(html_doc, encoding="utf-8")
    (BASE_DIR / "report_template.html").write_text(html_doc, encoding="utf-8")
    return dest


def generate_html_report() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = list_detections(include_deleted=True)
    items = _build_items(rows)
    track = _load_track_for_report(rows)
    map_svg = _svg_flight_map(track, items)
    hw = hardware_spec()
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    span = max((float(r.get("time_sec") or 0) for r in rows), default=0.0)
    html_doc = render_report_html(
        created=created,
        operator_id=_operator_id(rows),
        source_video=_video_label(rows),
        model_name=_active_model_name(),
        duration=_fmt_time(span),
        platform=_platform_label(hw),
        items=items,
        map_svg=map_svg,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = REPORTS_DIR / f"muravei_report_{stamp}.html"
    dest.write_text(html_doc, encoding="utf-8")
    (REPORTS_DIR / "latest.html").write_text(html_doc, encoding="utf-8")
    print(f"[REPORT] wrote {dest} n={len(rows)}")
    return dest


def generate_pdf_report() -> Path:
    """Technical PDF: header, primitive lon/lat scatter map, counts, detection table.

    This is a schematic, not a pretty map — KML is the primary geo format.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = list_detections(include_deleted=False)
    items = _build_items(rows)
    hw = hardware_spec()
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = REPORTS_DIR / f"muravei_report_{stamp}.pdf"

    styles = getSampleStyleSheet()
    story: list[Any] = []
    story.append(Paragraph("MuraveiVision PRO — detection report", styles["Title"]))
    story.append(Paragraph(
        f"{created} · operator={_esc(_operator_id(rows))} · "
        f"video={_esc(_video_label(rows))} · model={_esc(_active_model_name())} · "
        f"{_esc(_platform_label(hw))}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 8))

    counts = Counter(str(it.get("op_class") or "unknown") for it in items)
    count_rows = [["Class", "N"]] + [[k, str(v)] for k, v in counts.most_common(20)]
    count_table = Table(count_rows, colWidths=[120 * mm, 40 * mm])
    count_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
    ]))
    story.append(Paragraph(f"Detections: {len(items)} (not deleted)", styles["Heading2"]))
    story.append(count_table)
    story.append(Spacer(1, 10))

    geotagged = [
        it for it in items
        if it.get("gps_lat") is not None and it.get("gps_lon") is not None
    ]
    story.append(Paragraph(
        f"GPS map (schematic, {len(geotagged)} points) — open KML in Google Earth for a real map",
        styles["Heading2"],
    ))

    # Primitive scatter drawn into a separate page-sized canvas via a flowable-like table spacer.
    # We'll paint the map after build using a canvas callback.
    map_lons = [float(it["gps_lon"]) for it in geotagged]
    map_lats = [float(it["gps_lat"]) for it in geotagged]
    map_cls = [str(it.get("op_class") or "") for it in geotagged]

    det_rows = [["Time", "Class", "Conf%", "Lat", "Lon"]]
    for it in items[:80]:
        det_rows.append([
            str(it.get("ts") or ""),
            str(it.get("op_class") or "")[:40],
            str(it.get("conf") or ""),
            "" if it.get("gps_lat") is None else f"{float(it['gps_lat']):.5f}",
            "" if it.get("gps_lon") is None else f"{float(it['gps_lon']):.5f}",
        ])
    det_table = Table(det_rows, colWidths=[28 * mm, 70 * mm, 18 * mm, 35 * mm, 35 * mm])
    det_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    story.append(Spacer(1, 8))
    story.append(det_table)

    def _draw_map(canv: pdf_canvas.Canvas, _doc: Any) -> None:
        if not map_lons:
            canv.setFont("Helvetica", 8)
            canv.setFillColor(colors.grey)
            canv.drawString(20 * mm, 40 * mm, "No geotagged detections — map empty")
            return
        x0, y0, w, h = 20 * mm, 18 * mm, 170 * mm, 55 * mm
        canv.setStrokeColor(colors.HexColor("#111827"))
        canv.setFillColor(colors.HexColor("#fafafa"))
        canv.rect(x0, y0, w, h, fill=1, stroke=1)
        min_lon, max_lon = min(map_lons), max(map_lons)
        min_lat, max_lat = min(map_lats), max(map_lats)
        pad_lon = max((max_lon - min_lon) * 0.08, 1e-5)
        pad_lat = max((max_lat - min_lat) * 0.08, 1e-5)
        min_lon -= pad_lon
        max_lon += pad_lon
        min_lat -= pad_lat
        max_lat += pad_lat
        dx = max(max_lon - min_lon, 1e-9)
        dy = max(max_lat - min_lat, 1e-9)
        palette = [
            colors.HexColor("#ef4444"),
            colors.HexColor("#3b82f6"),
            colors.HexColor("#f59e0b"),
            colors.HexColor("#10b981"),
            colors.HexColor("#a855f7"),
        ]
        for lon, lat, cls in zip(map_lons, map_lats, map_cls):
            px = x0 + ((lon - min_lon) / dx) * w
            py = y0 + ((lat - min_lat) / dy) * h
            canv.setFillColor(palette[abs(hash(cls)) % len(palette)])
            canv.circle(px, py, 2.2, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor("#111827"))
        canv.setFont("Helvetica", 7)
        canv.drawString(x0, y0 - 10, f"lon [{min_lon:.5f} .. {max_lon:.5f}]  lat [{min_lat:.5f} .. {max_lat:.5f}]")

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=70 * mm,
    )
    doc.build(story, onFirstPage=_draw_map, onLaterPages=_draw_map)
    (REPORTS_DIR / "latest.pdf").write_bytes(dest.read_bytes())
    print(f"[REPORT] wrote {dest} n={len(rows)} geotagged={len(geotagged)}")
    return dest
