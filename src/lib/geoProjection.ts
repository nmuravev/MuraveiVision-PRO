/** Simplified local ENU projection for Flight3D (not WGS84→ECEF). */

export type TrackPoint = {
  timestamp: number;
  lat: number;
  lon: number;
  alt?: number;
  yaw?: number;
};

export type EnuOrigin = {
  lat0: number;
  lon0: number;
  cosLat: number;
};

export type Vec3 = { x: number; y: number; z: number };

const M_PER_DEG_LAT = 110540;
const M_PER_DEG_LON = 111320;

export function createEnuOrigin(lat0: number, lon0: number): EnuOrigin {
  return {
    lat0,
    lon0,
    cosLat: Math.cos((lat0 * Math.PI) / 180),
  };
}

/** Y-up: x=East, y=Up(alt), z=South (−North) for a familiar top-down orbit. */
export function latLonAltToVec3(
  lat: number,
  lon: number,
  alt: number,
  origin: EnuOrigin,
): Vec3 {
  const x = (lon - origin.lon0) * M_PER_DEG_LON * origin.cosLat;
  const z = -(lat - origin.lat0) * M_PER_DEG_LAT;
  const y = Number.isFinite(alt) ? alt : 0;
  return { x, y, z };
}

export function interpolateTrackAt(
  points: TrackPoint[],
  timeSec: number,
): TrackPoint | null {
  if (!points.length) return null;
  const pts = [...points].sort((a, b) => a.timestamp - b.timestamp);
  const t = timeSec;
  if (t <= pts[0].timestamp) return { ...pts[0] };
  if (t >= pts[pts.length - 1].timestamp) return { ...pts[pts.length - 1] };
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    if (a.timestamp <= t && t <= b.timestamp) {
      const span = b.timestamp - a.timestamp;
      const u = span <= 1e-9 ? 0 : (t - a.timestamp) / span;
      const out: TrackPoint = {
        timestamp: t,
        lat: a.lat + u * (b.lat - a.lat),
        lon: a.lon + u * (b.lon - a.lon),
        alt: (a.alt ?? 0) + u * ((b.alt ?? 0) - (a.alt ?? 0)),
      };
      if (a.yaw != null || b.yaw != null) {
        const ya = a.yaw ?? b.yaw ?? 0;
        const yb = b.yaw ?? a.yaw ?? ya;
        out.yaw = ya + u * (yb - ya);
      }
      return out;
    }
  }
  return { ...pts[pts.length - 1] };
}

export function formatTimecode(sec: number): string {
  const total = Math.max(0, Math.floor(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
