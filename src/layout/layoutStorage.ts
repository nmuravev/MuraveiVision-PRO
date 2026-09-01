import type { StateStorage } from 'zustand/middleware';
import type { MosaicNode } from 'react-mosaic-component';
import type { ViewId } from './initialLayout';
import { initialLayout, layoutPresets } from './initialLayout';

/** Stable forever — bump only with an explicit migration. */
export const LAYOUT_STORAGE_KEY = 'muraveivision-layout-v3';

const LEGACY_LAYOUT_KEYS = [
  'muraveivision-layout-v2',
  'muraveivision-layout-v1',
  'muraveivision-layout',
] as const;

export interface FloatingPanelState {
  id: ViewId;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PersistedLayout {
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
  closedPanels: ViewId[];
  preMaximizeTree: MosaicNode<ViewId> | null;
  maximizedId: ViewId | null;
}

/** One-time: v1/v2 → v3. Call before zustand persist hydrates. */
export function migrateLayoutStorage(): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(LAYOUT_STORAGE_KEY)) return;
    for (const key of LEGACY_LAYOUT_KEYS) {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      localStorage.setItem(LAYOUT_STORAGE_KEY, raw);
      localStorage.removeItem(key);
      console.info(`[layout] migrated ${key} → ${LAYOUT_STORAGE_KEY}`);
      return;
    }
  } catch (e) {
    console.warn('Failed to migrate layout storage', e);
  }
}

migrateLayoutStorage();

/** Debounced localStorage writes so drag/resize don't thrash disk. */
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let debouncePending: { name: string; value: string } | null = null;

function cancelDebouncedLayoutWrite(): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
  debouncePending = null;
}

export function createDebouncedLayoutStorage(delayMs = 300): StateStorage {
  const flush = () => {
    if (!debouncePending) return;
    try {
      localStorage.setItem(debouncePending.name, debouncePending.value);
    } catch (e) {
      console.warn('Failed to save layout', e);
    }
    debouncePending = null;
    debounceTimer = null;
  };

  return {
    getItem: (name) => {
      try {
        return localStorage.getItem(name);
      } catch {
        return null;
      }
    },
    setItem: (name, value) => {
      debouncePending = { name, value };
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(flush, delayMs);
    },
    removeItem: (name) => {
      cancelDebouncedLayoutWrite();
      try {
        localStorage.removeItem(name);
      } catch (e) {
        console.warn('Failed to clear layout', e);
      }
    },
  };
}

export function saveLayout(state: PersistedLayout): void {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn('Failed to save layout', e);
  }
}

export function loadLayout(): PersistedLayout | null {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedLayout;
  } catch (e) {
    console.warn('Failed to load layout', e);
    return null;
  }
}

export function clearLayout(): void {
  cancelDebouncedLayoutWrite();
  for (const key of [LAYOUT_STORAGE_KEY, ...LEGACY_LAYOUT_KEYS]) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  }
}

export function defaultPersistedLayout(): PersistedLayout {
  return {
    mosaicTree: layoutPresets.mediaView ?? initialLayout,
    floatingPanels: [],
    closedPanels: [],
    preMaximizeTree: null,
    maximizedId: null,
  };
}
