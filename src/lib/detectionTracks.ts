// KEEP: session trace — do not remove without explicit user order
/** Client-side detection tracks (in–out) — no DB migration. */
import type { PersistedDetection } from '../types/muravei';

const MAX_GAP_SEC = 2.5;
const MIN_IOU = 0.15;
const MAX_CENTER_DIST = 0.12; // normalized image coords (~50px on 640)

export type DetectionTrack = {
  trackId: string;
  class_name: string;
  tIn: number;
  tOut: number;
  duration_sec: number;
  count: number;
  primary: PersistedDetection;
  members: PersistedDetection[];
};

function boxIou(
  a: { bbox_x: number; bbox_y: number; bbox_w: number; bbox_h: number },
  b: { bbox_x: number; bbox_y: number; bbox_w: number; bbox_h: number },
): number {
  const ax2 = a.bbox_x + a.bbox_w;
  const ay2 = a.bbox_y + a.bbox_h;
  const bx2 = b.bbox_x + b.bbox_w;
  const by2 = b.bbox_y + b.bbox_h;
  const ix1 = Math.max(a.bbox_x, b.bbox_x);
  const iy1 = Math.max(a.bbox_y, b.bbox_y);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  const iw = Math.max(0, ix2 - ix1);
  const ih = Math.max(0, iy2 - iy1);
  const inter = iw * ih;
  const uni = a.bbox_w * a.bbox_h + b.bbox_w * b.bbox_h - inter;
  return uni > 0 ? inter / uni : 0;
}

function centerDist(
  a: { bbox_x: number; bbox_y: number; bbox_w: number; bbox_h: number },
  b: { bbox_x: number; bbox_y: number; bbox_w: number; bbox_h: number },
): number {
  const acx = a.bbox_x + a.bbox_w / 2;
  const acy = a.bbox_y + a.bbox_h / 2;
  const bcx = b.bbox_x + b.bbox_w / 2;
  const bcy = b.bbox_y + b.bbox_h / 2;
  return Math.hypot(acx - bcx, acy - bcy);
}

function canMerge(prev: PersistedDetection, next: PersistedDetection): boolean {
  if (prev.class_name !== next.class_name) return false;
  if (next.time_sec - prev.time_sec > MAX_GAP_SEC) return false;
  if (next.time_sec < prev.time_sec) return false;
  const iou = boxIou(prev, next);
  if (iou >= MIN_IOU) return true;
  return centerDist(prev, next) < MAX_CENTER_DIST;
}

/** Greedy tracks: same class, time gap ≤2.5s, IoU>0.15 or close centers. */
export function buildDetectionTracks(items: PersistedDetection[]): DetectionTrack[] {
  const sorted = [...items].sort((a, b) => a.time_sec - b.time_sec || a.id.localeCompare(b.id));
  const tracks: DetectionTrack[] = [];
  let seq = 0;

  for (const row of sorted) {
    const last = tracks[tracks.length - 1];
    const tip = last?.members[last.members.length - 1];
    if (last && tip && canMerge(tip, row)) {
      last.members.push(row);
      last.tOut = row.time_sec;
      last.duration_sec = Math.max(0, last.tOut - last.tIn);
      last.count = last.members.length;
      if (row.confidence >= last.primary.confidence) last.primary = row;
      continue;
    }
    seq += 1;
    tracks.push({
      trackId: `trk-${seq}-${row.id.slice(0, 8)}`,
      class_name: row.class_name,
      tIn: row.time_sec,
      tOut: row.time_sec,
      duration_sec: 0,
      count: 1,
      primary: row,
      members: [row],
    });
  }
  return tracks;
}

export function formatTrackRange(tIn: number, tOut: number): string {
  const fmt = (sec: number) => {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
  };
  if (Math.abs(tOut - tIn) < 0.05) return fmt(tIn);
  return `${fmt(tIn)} → ${fmt(tOut)}`;
}
