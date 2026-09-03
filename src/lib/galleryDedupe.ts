import type { PersistedDetection } from '../types/muravei';

export type GalleryGroup<T> = {
  key: string;
  primary: T;
  count: number;
};

export function galleryDedupeKey(row: {
  class_name: string;
  time_sec: number;
  bbox_x?: number;
  bbox_y?: number;
}): string {
  const t = Math.round(row.time_sec);
  const bx = Math.round((row.bbox_x ?? 0) * 20);
  const by = Math.round((row.bbox_y ?? 0) * 20);
  return `${row.class_name}|${t}|${bx}|${by}`;
}

export function groupGalleryDetections(
  items: PersistedDetection[],
): GalleryGroup<PersistedDetection>[] {
  const map = new Map<string, GalleryGroup<PersistedDetection>>();
  for (const row of items) {
    const key = galleryDedupeKey(row);
    const prev = map.get(key);
    if (prev) {
      prev.count += 1;
    } else {
      map.set(key, { key, primary: row, count: 1 });
    }
  }
  return [...map.values()];
}
