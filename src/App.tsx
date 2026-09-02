import React, { useCallback, useEffect, useState } from 'react';
import { Mosaic, MosaicWindow, type MosaicNode } from 'react-mosaic-component';
import 'react-mosaic-component/react-mosaic-component.css';
import { TopBar } from './components/TopBar';
import { ComponentForId } from './components/ComponentRegistry';
import { FloatingPanelHost } from './layout/FloatingPanelHost';
import { PanelChrome, PanelToolbarButtons } from './layout/PanelChrome';
import {
  MODE_TO_TAB,
  TAB_TO_MODE,
  VIEW_TITLES,
  layoutPresets,
  type ViewId,
} from './layout/initialLayout';
import { usePanelLayoutStore } from './store/usePanelLayoutStore';
import { usePlaybackClock } from './hooks/usePlaybackClock';
import { useHotkeys } from './hooks/useHotkeys';
import { useTimelineStore } from './store/timeline-store';
import { useViewerStore } from './store/useViewerStore';
import { useMuraveiStore } from './store/useMuraveiStore';
import { useSam3Store } from './store/useSam3Store';
import { SplashScreen, shouldShowSplash } from './components/SplashScreen';
import { ErrorDetailsModal } from './components/ErrorDetailsModal';
import {
  SHOW_ERROR_MODAL_EVENT,
  installApiErrorReporter,
  type ApiErrorDetails,
} from './lib/apiError';
import { logger } from './services/logger';

function App() {
  const mosaicTree = usePanelLayoutStore((s) => s.mosaicTree);
  const workspaceMode = usePanelLayoutStore((s) => s.workspaceMode);
  const setMosaicTree = usePanelLayoutStore((s) => s.setMosaicTree);
  const resetLayout = usePanelLayoutStore((s) => s.resetLayout);
  const setWorkspaceMode = usePanelLayoutStore((s) => s.setWorkspaceMode);
  const maximizedId = usePanelLayoutStore((s) => s.maximizedId);
  const [showSplash, setShowSplash] = useState(() => shouldShowSplash());
  const [layoutHydrated, setLayoutHydrated] = useState(
    () => usePanelLayoutStore.persist.hasHydrated(),
  );
  const [apiError, setApiError] = useState<ApiErrorDetails | null>(null);

  usePlaybackClock();
  useHotkeys();

  useEffect(() => installApiErrorReporter(), []);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<ApiErrorDetails>).detail;
      if (detail) setApiError(detail);
    };
    window.addEventListener(SHOW_ERROR_MODAL_EVENT, handler);
    return () => window.removeEventListener(SHOW_ERROR_MODAL_EVENT, handler);
  }, []);

  useEffect(() => {
    if (workspaceMode !== 'liveQuad') return;
    const { setSourceMode, viewers } = useViewerStore.getState();
    for (const id of ['viewer-1', 'viewer-2', 'viewer-3', 'viewer-4'] as const) {
      if (viewers[id]?.sourceMode !== 'live') setSourceMode(id, 'live');
    }
  }, [workspaceMode]);

  // Dev-only: expose stores for debugging and Playwright introspection.
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as Record<string, unknown>).__muraveiStores = {
      timeline: useTimelineStore,
      viewer: useViewerStore,
      muravei: useMuraveiStore,
      sam3: useSam3Store,
    };
  }, []);

  // Wait for localStorage rehydrate so Mosaic does not overwrite saved layout on F5
  useEffect(() => {
    if (usePanelLayoutStore.persist.hasHydrated()) {
      setLayoutHydrated(true);
      return;
    }
    return usePanelLayoutStore.persist.onFinishHydration(() => {
      setLayoutHydrated(true);
    });
  }, []);

  const activeTab = MODE_TO_TAB[workspaceMode] ?? 'Монтаж';

  const onTabChange = useCallback(
    (tab: string) => {
      const mode = TAB_TO_MODE[tab];
      if (mode) {
        setWorkspaceMode(mode);
        logger.debug('ui', `Вкладка → ${tab} (${mode})`);
      }
    },
    [setWorkspaceMode],
  );

  const handleResetLayout = useCallback(() => {
    if (
      !window.confirm(
        'Сбросить раскладку? Все сохранённые раскладки вкладок будут очищены, применится пресет «Медиа».',
      )
    ) {
      return;
    }
    resetLayout();
    logger.info('ui', 'Раскладка сброшена');
  }, [resetLayout]);

  const renderTile = useCallback(
    (id: ViewId, path: number[]) => (
      <MosaicWindow<ViewId>
        path={path}
        title={VIEW_TITLES[id]}
        toolbarControls={<PanelToolbarButtons id={id} />}
      >
        <PanelChrome id={id} hideHeader>
          <ComponentForId id={id} />
        </PanelChrome>
      </MosaicWindow>
    ),
    [],
  );

  const fallbackTree = layoutPresets.mediaView;

  return (
    <div className="h-screen max-h-screen w-screen flex flex-col overflow-hidden bg-[var(--dv-bg-deep)] text-[var(--dv-text)]">
      {showSplash && (
        <SplashScreen
          onDone={() => {
            setShowSplash(false);
            logger.info('app', 'Splash скрыт — UI готов');
          }}
        />
      )}
      <TopBar
        activeTab={activeTab}
        onTabChange={onTabChange}
        isDefaultLayout={!maximizedId}
        onResetLayout={handleResetLayout}
      />
      <div className="flex-1 min-h-0 relative mosaic-root">
        {!layoutHydrated ? (
          <div className="h-full flex items-center justify-center text-xs text-[var(--dv-text-muted)]">
            Восстановление раскладки…
          </div>
        ) : (
          <>
            <Mosaic<ViewId>
              className="muravei-mosaic"
              value={mosaicTree ?? fallbackTree}
              onChange={(node: MosaicNode<ViewId> | null) => setMosaicTree(node)}
              renderTile={renderTile}
              resize={{ minimumPaneSizePercentage: 8 }}
            />
            <FloatingPanelHost />
          </>
        )}
      </div>
      <ErrorDetailsModal error={apiError} onClose={() => setApiError(null)} />
    </div>
  );
}

export default App;
