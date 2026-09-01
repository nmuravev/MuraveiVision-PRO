/** Local tangent-plane projection (metres). Not WGS84 ECEF. */
export type GeoPoint = {
  timestamp: number;
  lat: number;
  lon: number;
  alt?: number;
  yaw?: number;
};

export type LocalOrigin = {
  lat0: number;
  lon0: number;
  alt0: number;
};

const R = 6378137; // WGS84 equatorial radius (m)

export function makeOrigin(points: GeoPoint[]): LocalOrigin | null {
  if (!points.length) return null;
  const lat0 = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const lon0 = points.reduce((s, p) => s + p.lon, 0) / points.length;
  const alts = points.map((p) => p.alt ?? 0);
  const alt0 = Math.min(...alts);
  return { lat0, lon0, alt0 };
}

/** X = East, Y = Up, Z = South (Three.js Y-up). */
export function toLocal(
  lat: number,
  lon: number,
  alt: number,
  origin: LocalOrigin,
): { x: number; y: number; z: number } {
  const dLat = ((lat - origin.lat0) * Math.PI) / 180;
  const dLon = ((lon - origin.lon0) * Math.PI) / 180;
  const cosLat = Math.cos((origin.lat0 * Math.PI) / 180);
  const x = dLon * cosLat * R;
  const z = -dLat * R;
  const y = (alt ?? 0) - origin.alt0;
  return { x, y, z };
}

export function interpolateTrack(track: GeoPoint[], timeSec: number): GeoPoint | null {
  if (!track.length) return null;
  const pts = [...track].sort((a, b) => a.timestamp - b.timestamp);
  if (timeSec <= pts[0].timestamp) return { ...pts[0] };
  if (timeSec >= pts[pts.length - 1].timestamp) return { ...pts[pts.length - 1] };
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    if (a.timestamp <= timeSec && timeSec <= b.timestamp) {
      const span = b.timestamp - a.timestamp || 1;
      const u = (timeSec - a.timestamp) / span;
      const out: GeoPoint = {
        timestamp: timeSec,
        lat: a.lat + u * (b.lat - a.lat),
        lon: a.lon + u * (b.lon - a.lon),
        alt: (a.alt ?? 0) + u * ((b.alt ?? 0) - (a.alt ?? 0)),
      };
      if (a.yaw != null || b.yaw != null) {
        out.yaw = (a.yaw ?? 0) + u * ((b.yaw ?? a.yaw ?? 0) - (a.yaw ?? 0));
      }
      return out;
    }
  }
  return { ...pts[pts.length - 1] };
}

export function formatTimecode(sec: number): string {
  const t = Math.max(0, Math.floor(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
