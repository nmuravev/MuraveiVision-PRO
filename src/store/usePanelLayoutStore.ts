import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { MosaicNode } from 'react-mosaic-component';
import { getLeaves } from 'react-mosaic-component';
import {
  ALL_VIEW_IDS,
  initialLayout,
  layoutPresets,
  type ViewId,
  type WorkspaceMode,
} from '../layout/initialLayout';
import type { FloatingPanelState } from '../layout/layoutStorage';
import {
  LAYOUT_STORAGE_KEY,
  clearLayout,
  createDebouncedLayoutStorage,
} from '../layout/layoutStorage';
import { removeLeaf, sanitizeMosaicTree } from '../layout/layoutActions';

interface ModeSnapshot {
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
  closedPanels: ViewId[];
}

interface PanelLayoutState {
  workspaceMode: WorkspaceMode;
  modeLayouts: Partial<Record<WorkspaceMode, ModeSnapshot>>;
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
  closedPanels: ViewId[];
  preMaximizeTree: MosaicNode<ViewId> | null;
  maximizedId: ViewId | null;
  setMosaicTree: (tree: MosaicNode<ViewId> | null) => void;
  maximizePanel: (id: ViewId) => void;
  restoreLayout: () => void;
  closePanel: (id: ViewId) => void;
  openPanel: (id: ViewId) => void;
  undockPanel: (id: ViewId, rect?: Partial<FloatingPanelState>) => void;
  redockPanel: (id: ViewId) => void;
  updateFloating: (id: ViewId, patch: Partial<FloatingPanelState>) => void;
  applyPreset: (name: string) => void;
  setWorkspaceMode: (mode: WorkspaceMode) => void;
  resetLayout: () => void;
  isPanelVisible: (id: ViewId) => boolean;
}

function collectVisible(state: {
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
}): Set<ViewId> {
  const set = new Set<ViewId>();
  if (state.mosaicTree) {
    try {
      for (const leaf of getLeaves(state.mosaicTree)) {
        set.add(leaf);
      }
    } catch {
      /* corrupt tree */
    }
  }
  for (const f of state.floatingPanels) set.add(f.id);
  return set;
}

function snapshotOf(state: {
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
  closedPanels: ViewId[];
}): ModeSnapshot {
  return {
    mosaicTree: state.mosaicTree,
    floatingPanels: state.floatingPanels,
    closedPanels: state.closedPanels,
  };
}

function defaultForMode(mode: WorkspaceMode): ModeSnapshot {
  return {
    mosaicTree: layoutPresets[mode] ?? initialLayout,
    floatingPanels: [],
    closedPanels: [],
  };
}

const mediaDefault = layoutPresets.mediaView ?? initialLayout;

export const usePanelLayoutStore = create<PanelLayoutState>()(
  persist(
    (set, get) => ({
      workspaceMode: 'mediaView',
      modeLayouts: {},
      mosaicTree: mediaDefault,
      floatingPanels: [],
      closedPanels: [],
      preMaximizeTree: null,
      maximizedId: null,

      setMosaicTree: (tree) => {
        const { workspaceMode, modeLayouts } = get();
        const mosaicTree = sanitizeMosaicTree(tree);
        set({
          mosaicTree,
          modeLayouts: {
            ...modeLayouts,
            [workspaceMode]: {
              mosaicTree,
              floatingPanels: get().floatingPanels,
              closedPanels: get().closedPanels,
            },
          },
        });
      },

      maximizePanel: (id) => {
        const { mosaicTree, maximizedId, preMaximizeTree } = get();
        if (maximizedId === id) {
          set({
            mosaicTree: preMaximizeTree ?? initialLayout,
            maximizedId: null,
            preMaximizeTree: null,
          });
          return;
        }
        // restore-then-maximize: never overwrite preMaximize with a leaf
        const baseTree = maximizedId ? (preMaximizeTree ?? mosaicTree) : mosaicTree;
        set({
          preMaximizeTree: baseTree,
          mosaicTree: id,
          maximizedId: id,
        });
      },

      restoreLayout: () => {
        const { preMaximizeTree } = get();
        set({
          mosaicTree: preMaximizeTree ?? initialLayout,
          maximizedId: null,
          preMaximizeTree: null,
        });
      },

      closePanel: (id) => {
        const state = get();
        const mosaicTree = removeLeaf(state.mosaicTree, id);
        const floatingPanels = state.floatingPanels.filter((f) => f.id !== id);
        const closedPanels = state.closedPanels.includes(id)
          ? state.closedPanels
          : [...state.closedPanels, id];
        set({
          mosaicTree,
          floatingPanels,
          closedPanels,
          maximizedId: state.maximizedId === id ? null : state.maximizedId,
          modeLayouts: {
            ...state.modeLayouts,
            [state.workspaceMode]: { mosaicTree, floatingPanels, closedPanels },
          },
        });
      },

      openPanel: (id) => {
        const state = get();
        const visible = collectVisible(state);
        if (visible.has(id)) return;
        const closedPanels = state.closedPanels.filter((c) => c !== id);
        let mosaicTree: MosaicNode<ViewId>;
        if (!state.mosaicTree) {
          mosaicTree = id;
        } else {
          mosaicTree = {
            type: 'split',
            direction: 'row',
            splitPercentages: [75, 25],
            children: [state.mosaicTree, id],
          };
        }
        set({
          mosaicTree,
          closedPanels,
          modeLayouts: {
            ...state.modeLayouts,
            [state.workspaceMode]: {
              mosaicTree,
              floatingPanels: state.floatingPanels,
              closedPanels,
            },
          },
        });
      },

      undockPanel: (id, rect) => {
        const state = get();
        const mosaicTree = removeLeaf(state.mosaicTree, id);
        const existing = state.floatingPanels.find((f) => f.id === id);
        const panel: FloatingPanelState = existing ?? {
          id,
          x: rect?.x ?? 120,
          y: rect?.y ?? 80,
          w: rect?.w ?? 480,
          h: rect?.h ?? 360,
        };
        const floatingPanels = [
          ...state.floatingPanels.filter((f) => f.id !== id),
          panel,
        ];
        const closedPanels = state.closedPanels.filter((c) => c !== id);
        set({
          mosaicTree,
          floatingPanels,
          closedPanels,
          modeLayouts: {
            ...state.modeLayouts,
            [state.workspaceMode]: { mosaicTree, floatingPanels, closedPanels },
          },
        });
      },

      redockPanel: (id) => {
        const state = get();
        const floatingPanels = state.floatingPanels.filter((f) => f.id !== id);
        let mosaicTree: MosaicNode<ViewId>;
        if (!state.mosaicTree) {
          mosaicTree = id;
        } else {
          mosaicTree = {
            type: 'split',
            direction: 'row',
            splitPercentages: [70, 30],
            children: [state.mosaicTree, id],
          };
        }
        set({
          mosaicTree,
          floatingPanels,
          modeLayouts: {
            ...state.modeLayouts,
            [state.workspaceMode]: {
              mosaicTree,
              floatingPanels,
              closedPanels: state.closedPanels,
            },
          },
        });
      },

      updateFloating: (id, patch) => {
        set((state) => {
          const floatingPanels = state.floatingPanels.map((f) =>
            f.id === id ? { ...f, ...patch } : f,
          );
          return {
            floatingPanels,
            modeLayouts: {
              ...state.modeLayouts,
              [state.workspaceMode]: {
                mosaicTree: state.mosaicTree,
                floatingPanels,
                closedPanels: state.closedPanels,
              },
            },
          };
        });
      },

      applyPreset: (name) => {
        const tree = layoutPresets[name] ?? initialLayout;
        const mode = (['mediaView', 'editDefault', 'aiAnalysis', 'training', 'system'].includes(
          name,
        )
          ? name
          : get().workspaceMode) as WorkspaceMode;
        const snap: ModeSnapshot = {
          mosaicTree: tree,
          floatingPanels: [],
          closedPanels: [],
        };
        set({
          workspaceMode: mode,
          mosaicTree: tree,
          floatingPanels: [],
          closedPanels: [],
          maximizedId: null,
          preMaximizeTree: null,
          modeLayouts: { ...get().modeLayouts, [mode]: snap },
        });
      },

      setWorkspaceMode: (mode) => {
        const state = get();
        if (state.workspaceMode === mode) return;
        const savedCurrent = {
          ...state.modeLayouts,
          [state.workspaceMode]: snapshotOf(state),
        };
        const next = savedCurrent[mode] ?? defaultForMode(mode);
        set({
          workspaceMode: mode,
          modeLayouts: savedCurrent,
          mosaicTree: sanitizeMosaicTree(next.mosaicTree),
          floatingPanels: next.floatingPanels,
          closedPanels: next.closedPanels,
          maximizedId: null,
          preMaximizeTree: null,
        });
      },

      resetLayout: () => {
        clearLayout();
        const snap = defaultForMode('mediaView');
        set({
          workspaceMode: 'mediaView',
          mosaicTree: snap.mosaicTree,
          floatingPanels: [],
          closedPanels: [],
          maximizedId: null,
          preMaximizeTree: null,
          modeLayouts: { mediaView: snap },
        });
      },

      isPanelVisible: (id) => {
        const state = get();
        return collectVisible(state).has(id);
      },
    }),
    {
      name: LAYOUT_STORAGE_KEY,
      storage: createJSONStorage(() => createDebouncedLayoutStorage(300)),
      partialize: (s) => ({
        workspaceMode: s.workspaceMode,
        modeLayouts: s.modeLayouts,
        mosaicTree: s.mosaicTree,
        floatingPanels: s.floatingPanels,
        closedPanels: s.closedPanels,
        preMaximizeTree: s.preMaximizeTree,
        maximizedId: s.maximizedId,
      }),
      merge: (persisted, current) => {
        const p = persisted as Partial<PanelLayoutState> | undefined;
        if (!p) return current;
        const stripQueue = (tree: MosaicNode<ViewId> | null) =>
          tree ? removeLeaf(sanitizeMosaicTree(tree), 'queue') : null;
        const modeLayouts: Partial<Record<WorkspaceMode, ModeSnapshot>> = p.modeLayouts
          ? (Object.fromEntries(
              Object.entries(p.modeLayouts).map(([mode, snap]) => [
                mode,
                snap
                  ? { ...snap, mosaicTree: stripQueue(snap.mosaicTree) }
                  : snap,
              ]),
            ) as Partial<Record<WorkspaceMode, ModeSnapshot>>)
          : current.modeLayouts;
        return {
          ...current,
          ...p,
          mosaicTree: stripQueue(p.mosaicTree ?? current.mosaicTree),
          modeLayouts,
        };
      },
    },
  ),
);

export function getMissingPanels(state: {
  mosaicTree: MosaicNode<ViewId> | null;
  floatingPanels: FloatingPanelState[];
}): ViewId[] {
  const visible = collectVisible(state);
  return ALL_VIEW_IDS.filter((id) => !visible.has(id));
}
