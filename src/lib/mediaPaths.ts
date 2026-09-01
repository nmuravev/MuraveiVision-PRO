/** Normalize archive paths for cross-component matching (Windows vs POSIX). */
export function normMediaPath(p: string): string {
  let s = p
    .split(/[?#]/, 1)[0]
    .replace(/\\/g, '/')
    .toLowerCase()
    .replace(/^\/+/, '');
  const archiveMarker = '/archive/';
  const archiveIndex = s.lastIndexOf(archiveMarker);
  if (archiveIndex >= 0) s = s.slice(archiveIndex + archiveMarker.length);
  else if (s.startsWith('archive/')) s = s.slice('archive/'.length);
  return s;
}

export function mediaPathsMatch(a: string, b: string): boolean {
  if (!a || !b) return false;
  const na = normMediaPath(a);
  const nb = normMediaPath(b);
  return Boolean(na && na === nb);
}

export function formatMediaTime(sec: number): string {
  const s = Math.max(0, sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = Math.floor(s % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}
